from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aiogram import Bot

from database import DEFAULT_DB_PATH, connect
from services.economy import _balance, _change_balance

LOAN_PRINCIPAL = 50
LOAN_INTEREST_PERCENT = 10
LOAN_DUE_AMOUNT = LOAN_PRINCIPAL * (100 + LOAN_INTEREST_PERCENT) // 100
LOAN_TERM_SECONDS = 30 * 60
LOAN_COOLDOWN_SECONDS = 60 * 60
LOAN_WORKER_INTERVAL_SECONDS = 30

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoanDecision:
    status: Literal["granted", "active", "cooldown", "debt"]
    balance: int
    due_at: int | None = None
    available_at: int | None = None

    def remaining_minutes(self, now: int) -> int:
        timestamp = self.due_at or self.available_at or now
        return max(1, math.ceil((timestamp - now) / 60))


@dataclass(frozen=True, slots=True)
class LoanSettlement:
    chat_id: int
    user_id: int
    due_amount: int
    balance: int
    user_name: str


def _settle_active_loan(
    connection,
    loan,
    settled_at: int,
) -> LoanSettlement | None:
    updated = connection.execute(
        """
        UPDATE loans
        SET status = 'settled', settled_at = ?
        WHERE id = ? AND status = 'active'
        """,
        (settled_at, loan["id"]),
    )
    if updated.rowcount != 1:
        return None

    balance = _change_balance(
        connection,
        operation_key=f"loan:{loan['id']}:settlement",
        chat_id=int(loan["chat_id"]),
        user_id=int(loan["user_id"]),
        delta=-int(loan["due_amount"]),
        kind="loan_repayment",
        reference_id=str(loan["id"]),
        allow_debt=True,
    )
    user = connection.execute(
        "SELECT full_name FROM users WHERE chat_id = ? AND user_id = ?",
        (loan["chat_id"], loan["user_id"]),
    ).fetchone()
    user_name = user["full_name"] if user and user["full_name"] else str(loan["user_id"])

    return LoanSettlement(
        chat_id=loan["chat_id"],
        user_id=loan["user_id"],
        due_amount=loan["due_amount"],
        balance=balance.balance,
        user_name=user_name,
    )


def issue_loan(
    chat_id: int,
    user_id: int,
    *,
    now: int | None = None,
    db_path: str | Path | None = None,
) -> LoanDecision:
    current_time = int(time.time()) if now is None else now
    database_path = db_path or DEFAULT_DB_PATH

    with connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        active_loan = connection.execute(
            """
            SELECT id, chat_id, user_id, due_amount, due_at
            FROM loans
            WHERE chat_id = ? AND user_id = ? AND status = 'active'
            """,
            (chat_id, user_id),
        ).fetchone()

        if active_loan and active_loan["due_at"] <= current_time:
            _settle_active_loan(connection, active_loan, current_time)
            active_loan = None

        balance = _balance(connection, chat_id, user_id)

        if active_loan:
            return LoanDecision(
                status="active",
                balance=balance,
                due_at=active_loan["due_at"],
            )

        if balance < 0:
            return LoanDecision(status="debt", balance=balance)

        previous_loan = connection.execute(
            """
            SELECT next_loan_at
            FROM loans
            WHERE chat_id = ? AND user_id = ?
            ORDER BY issued_at DESC, id DESC
            LIMIT 1
            """,
            (chat_id, user_id),
        ).fetchone()
        if previous_loan and previous_loan["next_loan_at"] > current_time:
            return LoanDecision(
                status="cooldown",
                balance=balance,
                available_at=previous_loan["next_loan_at"],
            )

        due_at = current_time + LOAN_TERM_SECONDS
        next_loan_at = due_at + LOAN_COOLDOWN_SECONDS
        inserted = connection.execute(
            """
            INSERT INTO loans (
                chat_id, user_id, principal, due_amount,
                issued_at, due_at, next_loan_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                user_id,
                LOAN_PRINCIPAL,
                LOAN_DUE_AMOUNT,
                current_time,
                due_at,
                next_loan_at,
            ),
        )
        loan_id = int(inserted.lastrowid)
        credited = _change_balance(
            connection,
            operation_key=f"loan:{loan_id}:principal",
            chat_id=chat_id,
            user_id=user_id,
            delta=LOAN_PRINCIPAL,
            kind="loan_principal",
            reference_id=str(loan_id),
        )

        return LoanDecision(
            status="granted",
            balance=credited.balance,
            due_at=due_at,
            available_at=next_loan_at,
        )


def settle_due_loans(
    *,
    now: int | None = None,
    db_path: str | Path | None = None,
    limit: int = 100,
) -> list[LoanSettlement]:
    current_time = int(time.time()) if now is None else now
    database_path = db_path or DEFAULT_DB_PATH

    with connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        loans = connection.execute(
            """
            SELECT id, chat_id, user_id, due_amount, due_at
            FROM loans
            WHERE status = 'active' AND due_at <= ?
            ORDER BY due_at, id
            LIMIT ?
            """,
            (current_time, limit),
        ).fetchall()

        settlements = [
            settlement
            for loan in loans
            if (settlement := _settle_active_loan(connection, loan, current_time))
            is not None
        ]

    return settlements


async def _notify_settlement(bot: Bot, settlement: LoanSettlement) -> None:
    if settlement.balance < 0:
        message = (
            f"🏦 Срок займа истёк: с {settlement.user_name} списано "
            f"{settlement.due_amount} 🥔.\n"
            f"Баланс: {settlement.balance} 🥔. Новый займ будет доступен "
            "после погашения долга и окончания таймера."
        )
    else:
        message = (
            f"🏦 {settlement.user_name} вернул займ с процентами: "
            f"списано {settlement.due_amount} 🥔."
        )

    try:
        await bot.send_message(settlement.chat_id, message)
    except Exception:
        logger.exception(
            "Failed to send loan settlement notification",
            extra={
                "chat_id": settlement.chat_id,
                "user_id": settlement.user_id,
            },
        )


async def run_loan_worker(bot: Bot) -> None:
    while True:
        try:
            settlements = await asyncio.to_thread(settle_due_loans)
            for settlement in settlements:
                await _notify_settlement(bot, settlement)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Loan worker iteration failed")

        await asyncio.sleep(LOAN_WORKER_INTERVAL_SECONDS)
