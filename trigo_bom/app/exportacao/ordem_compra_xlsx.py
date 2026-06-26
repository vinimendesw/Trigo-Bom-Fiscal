import json
from openpyxl import Workbook
from openpyxl.styles import Font
from db import repositorio


def exportar_itens_oc(ordem_compra_id: int, caminho_destino: str) -> str:
    itens = json.loads(repositorio.listar_itens_oc(ordem_compra_id))

    wb = Workbook()
    ws = wb.active
    ws.title = "Itens OC"

    cabecalho = ["#", "Descrição", "Quantidade", "Valor Unitário", "Valor Total"]
    ws.append(cabecalho)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for i, item in enumerate(itens, start=1):
        ws.append([
            i,
            item.get("descricao", ""),
            item.get("quantidade"),
            item.get("valor_unitario"),
            item.get("valor_total"),
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    wb.save(caminho_destino)
    return json.dumps({"ok": True, "arquivo": caminho_destino})
