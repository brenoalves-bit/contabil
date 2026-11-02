from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from app.core.errors import Conflict, NotFound
from app.models import Empresa, PapelEmpresa, Usuario, UsuarioEmpresa
from app.schemas.empresa import EmpresaCreate, EmpresaUpdate
from app.services import auditoria, contas


def criar(db: Session, dados: EmpresaCreate, *, usuario: Usuario, ip: str | None) -> Empresa:
    if db.scalar(select(Empresa.id).where(Empresa.cnpj == dados.cnpj)):
        raise Conflict("CNPJ já cadastrado")
    e = Empresa(
        razao_social=dados.razao_social,
        nome_fantasia=dados.nome_fantasia,
        cnpj=dados.cnpj,
        regime_tributario=dados.regime_tributario,
        inicio_exercicio_mes=dados.inicio_exercicio_mes,
    )
    db.add(e)
    db.flush()
    auditoria.registrar(
        db, acao="criar", entidade="empresa", entidade_id=e.id, empresa_id=e.id,
        usuario_id=usuario.id, dados={"cnpj": e.cnpj, "razao_social": e.razao_social}, ip=ip,
    )
    if dados.criar_plano_padrao:
        set_tenant(db, e.id, usuario.id)
        contas.criar_plano_padrao(db, e.id)
    return e


def obter(db: Session, empresa_id: UUID) -> Empresa:
    e = db.get(Empresa, empresa_id)
    if e is None:
        raise NotFound("empresa não encontrada")
    return e


def listar_para_usuario(db: Session, usuario: Usuario) -> list[Empresa]:
    if usuario.admin_escritorio:
        return list(db.scalars(select(Empresa).order_by(Empresa.razao_social)))
    q = (
        select(Empresa)
        .join(UsuarioEmpresa, UsuarioEmpresa.empresa_id == Empresa.id)
        .where(UsuarioEmpresa.usuario_id == usuario.id)
        .order_by(Empresa.razao_social)
    )
    return list(db.scalars(q))


def atualizar(db: Session, e: Empresa, dados: EmpresaUpdate, *, usuario: Usuario, ip: str | None) -> Empresa:
    mudancas = dados.model_dump(exclude_unset=True)
    for k, v in mudancas.items():
        setattr(e, k, v)
    auditoria.registrar(
        db, acao="atualizar", entidade="empresa", entidade_id=e.id, empresa_id=e.id,
        usuario_id=usuario.id, dados=mudancas, ip=ip,
    )
    return e


def papel_de(db: Session, usuario: Usuario, empresa_id: UUID) -> PapelEmpresa | None:
    if usuario.admin_escritorio:
        return PapelEmpresa.ADMIN
    v = db.get(UsuarioEmpresa, (usuario.id, empresa_id))
    return v.papel if v else None


def vincular_usuario(
    db: Session, empresa_id: UUID, usuario_id: UUID, papel: PapelEmpresa, *, por: Usuario, ip: str | None
) -> UsuarioEmpresa:
    if db.get(Usuario, usuario_id) is None:
        raise NotFound("usuário não encontrado")
    v = db.get(UsuarioEmpresa, (usuario_id, empresa_id))
    if v is None:
        v = UsuarioEmpresa(usuario_id=usuario_id, empresa_id=empresa_id, papel=papel)
        db.add(v)
    else:
        v.papel = papel
    auditoria.registrar(
        db, acao="vincular_usuario", entidade="usuario_empresa", entidade_id=usuario_id,
        empresa_id=empresa_id, usuario_id=por.id, dados={"papel": papel.value}, ip=ip,
    )
    return v


def desvincular_usuario(db: Session, empresa_id: UUID, usuario_id: UUID, *, por: Usuario, ip: str | None) -> None:
    v = db.get(UsuarioEmpresa, (usuario_id, empresa_id))
    if v is None:
        raise NotFound("vínculo não encontrado")
    db.delete(v)
    auditoria.registrar(
        db, acao="desvincular_usuario", entidade="usuario_empresa", entidade_id=usuario_id,
        empresa_id=empresa_id, usuario_id=por.id, ip=ip,
    )


def listar_vinculos(db: Session, empresa_id: UUID) -> list[tuple[UsuarioEmpresa, Usuario]]:
    q = (
        select(UsuarioEmpresa, Usuario)
        .join(Usuario, Usuario.id == UsuarioEmpresa.usuario_id)
        .where(UsuarioEmpresa.empresa_id == empresa_id)
        .order_by(Usuario.nome)
    )
    return [(v, u) for v, u in db.execute(q)]
