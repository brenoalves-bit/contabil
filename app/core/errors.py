class DomainError(Exception):
    status_code = 400
    code = "erro_dominio"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(DomainError):
    status_code = 404
    code = "nao_encontrado"


class Conflict(DomainError):
    status_code = 409
    code = "conflito"


class Forbidden(DomainError):
    status_code = 403
    code = "proibido"


class Unauthorized(DomainError):
    status_code = 401
    code = "nao_autenticado"


class RegraContabil(DomainError):
    """Violação de regra contábil: lançamento desbalanceado, período fechado, etc."""
    status_code = 422
    code = "regra_contabil"
