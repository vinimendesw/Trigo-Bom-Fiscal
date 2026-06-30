import json
from openpyxl import Workbook
from openpyxl.styles import Font
from db import repositorio


def exportar_itens_lista(lista_id: int, caminho_destino: str) -> str:
    """
    Exporta os itens AGREGADOS de uma lista de compras para .xlsx.
    As quantidades de itens com mesma descrição (normalizada) já vêm somadas
    pelo repositório.
    """
    listas = json.loads(repositorio.listar_listas_com_ocs())
    lista = next((l for l in listas if l["id"] == lista_id), None)
    if lista is None:
        return json.dumps({"ok": False, "erro": "Lista não encontrada"})

    itens = lista.get("itens_agregados", [])

    wb = Workbook()
    ws = wb.active
    ws.title = lista.get("nome", "Lista")

    cabecalho = ["#", "Descrição", "UN", "Quantidade", "Valor Unitário", "Valor Total"]
    ws.append(cabecalho)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for i, item in enumerate(itens, start=1):
        ws.append([
            i,
            item.get("descricao", ""),
            item.get("unidade", ""),
            item.get("quantidade"),
            item.get("valor_unitario"),
            item.get("valor_total"),
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    wb.save(caminho_destino)
    return json.dumps({"ok": True, "arquivo": caminho_destino})
