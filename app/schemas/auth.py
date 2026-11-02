from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=8, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str


class UsuarioCreate(BaseModel):
    email: EmailStr
    nome: str = Field(min_length=2, max_length=200)
    senha: str = Field(min_length=12, max_length=256)
    admin_escritorio: bool = False


class UsuarioOut(BaseModel):
    id: UUID
    email: str
    nome: str
    ativo: bool
    admin_escritorio: bool

    model_config = {"from_attributes": True}


class TrocarSenhaIn(BaseModel):
    senha_atual: str
    senha_nova: str = Field(min_length=12, max_length=256)
