from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    employee_no: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str
