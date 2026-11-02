from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DB, AdminEmpresa, Contador, Leitura
from app.core.errors import DomainError
from app.models import Conta, ModeloDocumento, StatusDocumento, TipoItem, TipoOperacao
from app.schemas.fiscal import (
    CancelarIn,
    DocumentoCreate,
    DocumentoOut,
    DocumentoPage,
    ImportacaoResultado,
    ItemPatchIn,
    ParticipanteCreate,
    ParticipanteOut,
    ParticipanteUpdate,
    PreviaContabilizacao,
    ProdutoCreate,
    ProdutoOut,
    ProdutoReferenciaIn,
    ProdutoReferenciaOut,
    ProdutoUpdate,
    RegraCreate,
    RegraLinhaOut,
    RegraOut,
    RegraUpdate,
    ResumoFiscalOut,
)
from app.services import empresas as svc_empresas
from app.services.fiscal import cadastros, contabilizacao
from app.services.fiscal import documentos as svc_docs

router = APIRouter(prefix="/empresas/{empresa_id}", tags=["fiscal"])


# ---------------------------------------------------------------- participantes
@router.get("/participantes", response_model=list[ParticipanteOut])
def listar_participantes(empresa_id: UUID, db: DB, ctx: Leitura, q: str | None = Query(default=None, max_length=100),
                         ativo: bool | None = None, limit: int = Query(default=100, ge=1, le=1000),
                         offset: int = Query(default=0, ge=0)):
    return cadastros.listar_participantes(db, ctx.empresa_id, q=q, ativo=ativo, limit=limit, offset=offset)


@router.post("/participantes", response_model=ParticipanteOut, status_code=status.HTTP_201_CREATED)
def criar_participante(empresa_id: UUID, dados: ParticipanteCreate, db: DB, ctx: Contador):
    return cadastros.criar_participante(db, ctx, dados)


@router.get("/participantes/{participante_id}", response_model=ParticipanteOut)
def obter_participante(empresa_id: UUID, participante_id: UUID, db: DB, ctx: Leitura):
    return cadastros.obter_participante(db, ctx.empresa_id, participante_id)


@router.patch("/participantes/{participante_id}", response_model=ParticipanteOut)
def atualizar_participante(empresa_id: UUID, participante_id: UUID, dados: ParticipanteUpdate, db: DB, ctx: Contador):
    return cadastros.atualizar_participante(db, ctx, participante_id, dados)


# ---------------------------------------------------------------- produtos
@router.get("/produtos", response_model=list[ProdutoOut])
def listar_produtos(empresa_id: UUID, db: DB, ctx: Leitura, q: str | None = Query(default=None, max_length=100),
                    tipo_item: TipoItem | None = None, ativo: bool | None = None,
                    limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)):
    return cadastros.listar_produtos(db, ctx.empresa_id, q=q, tipo_item=tipo_item, ativo=ativo, limit=limit, offset=offset)


@router.post("/produtos", response_model=ProdutoOut, status_code=status.HTTP_201_CREATED)
def criar_produto(empresa_id: UUID, dados: ProdutoCreate, db: DB, ctx: Contador):
    return cadastros.criar_produto(db, ctx, dados)


@router.get("/produtos/{produto_id}", response_model=ProdutoOut)
def obter_produto(empresa_id: UUID, produto_id: UUID, db: DB, ctx: Leitura):
    return cadastros.obter_produto(db, ctx.empresa_id, produto_id)


@router.patch("/produtos/{produto_id}", response_model=ProdutoOut)
def atualizar_produto(empresa_id: UUID, produto_id: UUID, dados: ProdutoUpdate, db: DB, ctx: Contador):
    return cadastros.atualizar_produto(db, ctx, produto_id, dados)


@router.get("/produtos/{produto_id}/referencias", response_model=list[ProdutoReferenciaOut])
def listar_referencias(empresa_id: UUID, produto_id: UUID, db: DB, ctx: Leitura):
    return cadastros.listar_referencias(db, ctx.empresa_id, produto_id)


@router.put("/produtos/{produto_id}/referencias", response_model=ProdutoReferenciaOut)
def criar_referencia(empresa_id: UUID, produto_id: UUID, dados: ProdutoReferenciaIn, db: DB, ctx: Contador):
    return cadastros.criar_referencia(db, ctx, produto_id, dados)


# ---------------------------------------------------------------- documentos fiscais
def _doc_out(doc) -> DocumentoOut:
    dados = {f: getattr(doc, f) for f in DocumentoOut.model_fields if f != "itens_sem_produto"}
    return DocumentoOut.model_validate({**dados, "itens_sem_produto": svc_docs.itens_sem_produto(doc)})


@router.get("/documentos-fiscais", response_model=DocumentoPage)
def listar_documentos(
    empresa_id: UUID, db: DB, ctx: Leitura, modelo: ModeloDocumento | None = None,
    tipo_operacao: TipoOperacao | None = None, status_: StatusDocumento | None = Query(default=None, alias="status"),
    data_inicio: date | None = None, data_fim: date | None = None, participante_id: UUID | None = None,
    contabilizado: bool | None = None, chave_acesso: str | None = Query(default=None, pattern=r"^[0-9]{44}$"),
    limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
):
    items, total = svc_docs.listar(
        db, ctx.empresa_id, modelo=modelo, tipo_operacao=tipo_operacao, status=status_, data_inicio=data_inicio,
        data_fim=data_fim, participante_id=participante_id, contabilizado=contabilizado, chave_acesso=chave_acesso,
        limit=limit, offset=offset)
    return DocumentoPage(items=items, total=total, limit=limit, offset=offset)


@router.post("/documentos-fiscais", response_model=DocumentoOut, status_code=status.HTTP_201_CREATED)
def criar_documento(empresa_id: UUID, dados: DocumentoCreate, db: DB, ctx: Contador):
    return _doc_out(svc_docs.criar_manual(db, ctx, dados))


@router.post("/documentos-fiscais/importar-xml", response_model=list[ImportacaoResultado])
async def importar_xml(empresa_id: UUID, db: DB, ctx: Contador, arquivos: Annotated[list[UploadFile], File(...)]):
    """Importa um ou mais XMLs de NF-e/NFC-e. Cada arquivo é processado isoladamente:
    um XML inválido não impede os demais."""
    resultados = []
    for arq in arquivos[:200]:
        conteudo = await arq.read()
        nome = arq.filename or "sem-nome.xml"
        savepoint = db.begin_nested()
        try:
            doc = svc_docs.importar_xml(db, ctx, conteudo)
            savepoint.commit()
            resultados.append(ImportacaoResultado(arquivo=nome, sucesso=True, documento_id=doc.id, chave_acesso=doc.chave_acesso))
        except DomainError as exc:
            if savepoint.is_active:
                savepoint.rollback()
            resultados.append(ImportacaoResultado(arquivo=nome, sucesso=False, erro=exc.message))
    return resultados


@router.get("/documentos-fiscais/resumo", response_model=ResumoFiscalOut)
def resumo(empresa_id: UUID, db: DB, ctx: Leitura, inicio: date = Query(...), fim: date = Query(...)):
    if fim < inicio:
        raise DomainError("fim deve ser maior ou igual a início", "intervalo_invalido")
    return svc_docs.resumo(db, ctx.empresa_id, inicio, fim)


@router.get("/documentos-fiscais/{documento_id}", response_model=DocumentoOut)
def obter_documento(empresa_id: UUID, documento_id: UUID, db: DB, ctx: Leitura):
    return _doc_out(svc_docs.obter(db, ctx.empresa_id, documento_id))


@router.get("/documentos-fiscais/{documento_id}/xml")
def obter_xml(empresa_id: UUID, documento_id: UUID, db: DB, ctx: Leitura):
    doc = svc_docs.obter(db, ctx.empresa_id, documento_id)
    if not doc.xml:
        raise DomainError("documento sem XML armazenado", "sem_xml")
    return Response(content=doc.xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{doc.chave_acesso or doc.id}.xml"'})


@router.delete("/documentos-fiscais/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_documento(empresa_id: UUID, documento_id: UUID, db: DB, ctx: Contador):
    svc_docs.excluir(db, ctx, documento_id)


@router.patch("/documentos-fiscais/{documento_id}/itens/{numero_item}", response_model=DocumentoOut)
def alterar_item(empresa_id: UUID, documento_id: UUID, numero_item: int, dados: ItemPatchIn, db: DB, ctx: Contador):
    """Vincula o item a um produto interno (gravando o de-para) e/ou corrige o CFOP de entrada."""
    return _doc_out(svc_docs.alterar_item(db, ctx, documento_id, numero_item, dados))


@router.post("/documentos-fiscais/{documento_id}/cancelar", response_model=DocumentoOut)
def cancelar_documento(empresa_id: UUID, documento_id: UUID, dados: CancelarIn, db: DB, ctx: Contador):
    return _doc_out(svc_docs.cancelar(db, ctx, documento_id, dados))


@router.get("/documentos-fiscais/{documento_id}/previa-contabilizacao", response_model=PreviaContabilizacao)
def previa(empresa_id: UUID, documento_id: UUID, db: DB, ctx: Leitura):
    return contabilizacao.previa(db, ctx, documento_id)


@router.post("/documentos-fiscais/{documento_id}/contabilizar", response_model=DocumentoOut)
def contabilizar(empresa_id: UUID, documento_id: UUID, db: DB, ctx: Contador, recontabilizar: bool = False):
    return _doc_out(contabilizacao.contabilizar(db, ctx, documento_id, recontabilizar=recontabilizar))


# ---------------------------------------------------------------- regras de contabilização
def _regra_out(db, r) -> RegraOut:
    ids = [ln.conta_id for ln in r.linhas]
    contas = {c.id: c for c in db.scalars(select(Conta).where(Conta.id.in_(ids)))} if ids else {}
    return RegraOut(
        id=r.id, nome=r.nome, prioridade=r.prioridade, ativa=r.ativa, modelo=r.modelo, tipo_operacao=r.tipo_operacao,
        cfops=r.cfops, tipo_item=r.tipo_item, contabilizar=r.contabilizar, historico_modelo=r.historico_modelo,
        linhas=[RegraLinhaOut(ordem=ln.ordem, componente=ln.componente, lado=ln.lado, conta_id=ln.conta_id,
                              conta_codigo=contas[ln.conta_id].codigo, conta_nome=contas[ln.conta_id].nome)
                for ln in r.linhas],
    )


@router.get("/regras-contabilizacao", response_model=list[RegraOut])
def listar_regras(empresa_id: UUID, db: DB, ctx: Leitura):
    return [_regra_out(db, r) for r in contabilizacao.listar_regras(db, ctx.empresa_id)]


@router.post("/regras-contabilizacao", response_model=RegraOut, status_code=status.HTTP_201_CREATED)
def criar_regra(empresa_id: UUID, dados: RegraCreate, db: DB, ctx: AdminEmpresa):
    return _regra_out(db, contabilizacao.criar_regra(db, ctx, dados))


@router.post("/regras-contabilizacao/padrao", status_code=status.HTTP_201_CREATED)
def regras_padrao(empresa_id: UUID, db: DB, ctx: AdminEmpresa, substituir: bool = False):
    e = svc_empresas.obter(db, ctx.empresa_id)
    return {"regras_criadas": contabilizacao.criar_regras_padrao(db, ctx, e.regime_tributario, substituir=substituir),
            "regime": e.regime_tributario.value}


@router.patch("/regras-contabilizacao/{regra_id}", response_model=RegraOut)
def atualizar_regra(empresa_id: UUID, regra_id: UUID, dados: RegraUpdate, db: DB, ctx: AdminEmpresa):
    return _regra_out(db, contabilizacao.atualizar_regra(db, ctx, regra_id, dados))


@router.delete("/regras-contabilizacao/{regra_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_regra(empresa_id: UUID, regra_id: UUID, db: DB, ctx: AdminEmpresa):
    contabilizacao.excluir_regra(db, ctx, regra_id)
