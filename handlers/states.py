from aiogram.fsm.state import StatesGroup, State

class BJState(StatesGroup):
    in_game = State()

class RPSState(StatesGroup):
    choosing = State()