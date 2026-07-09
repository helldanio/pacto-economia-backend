"""
Pacto pela Economia - Backend API
Este script utiliza FastAPI para gerir a integração entre o PWA e o Google Sheets.

Requisitos de Instalação:
pip install fastapi uvicorn gspread google-auth pydantic
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import gspread
from google.oauth2 import id_token
from google.auth.transport import requests
import json
import os

app = FastAPI(title="Pacto pela Economia API")

# Configuração de CORS (Para permitir que o PWA aceda à API a partir de qualquer domínio)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constantes e Configuração do Google
GOOGLE_CLIENT_ID = "762254097331-d10m55qm8aj9pcb0gb3l93l17rorcki2.apps.googleusercontent.com" 
# ID real da folha de cálculo
SHEET_ID = "1cB0lfgN7LGCTB9aXGIsud-HPJ-hBevB1W1gtPeLJG_s" 

# Ligar ao Google Sheets
try:
    gc = gspread.service_account(filename='credentials.json')
    planilha = gc.open_by_key(SHEET_ID)
    aba_cadastros = planilha.sheet1 # Assume que os dados vão para o primeiro separador
except Exception as e:
    print(f"Aviso: Não foi possível ligar ao Google Sheets. Verifique o credentials.json e o ID. Erro: {e}")
    aba_cadastros = None


# --- MODELOS DE DADOS (Mapeiam o JSON complexo do frontend) ---
class RecordModel(BaseModel):
    id: str
    agente_email: str
    data_cadastro: str
    sync_status: str
    identificacao: Dict[str, Any]
    composicao_familiar: Dict[str, Any]
    economia: Dict[str, Any]
    propriedade: Dict[str, Any]
    foco_produtivo: str
    apicultura: Optional[Dict[str, Any]] = None
    mandiocultura: Optional[Dict[str, Any]] = None
    demandas: Dict[str, Any]
    historico: Dict[str, Any]

# --- DEPENDÊNCIA DE AUTENTICAÇÃO ---
def verify_google_token(authorization: str = Header(None)):
    """
    Verifica o JWT enviado pelo frontend (Google Sign-In) ou o token manual.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return "agente@teste.com" # Utilizador de teste caso o cabeçalho não exista
        
    token = authorization.split(" ")[1]
    
    # Bypass para aceitar o login manual feito offline
    if token.startswith("manual_"):
        return token.replace("manual_", "") # Retorna o e-mail digitado manualmente

    # Se for o utilizador de simulação
    if token == "mock_token":
        return "agente@teste.com"

    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
        return idinfo['email']
    except ValueError:
        raise HTTPException(status_code=401, detail="Token inválido")

# --- ROTAS ---

@app.post("/api/cadastros/sync")
async def sync_cadastros(cadastros: List[RecordModel], user_email: str = Depends(verify_google_token)):
    """
    Recebe os cadastros offline do PWA e insere/atualiza na Folha de Cálculo.
    """
    if not aba_cadastros:
        raise HTTPException(status_code=500, detail="Google Sheets não configurado.")

    try:
        # Obtém todos os IDs existentes na coluna A para verificar duplicações
        coluna_ids = aba_cadastros.col_values(1)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao aceder à folha de cálculo: {str(e)}")

    linhas_para_inserir = []
    registros_atualizados = 0

    for cad in cadastros:
        # Segurança: Garante que o agente só sincroniza registos associados a ele
        if cad.agente_email != user_email:
            continue
            
        # TRATAMENTO DE DADOS COMPLEXOS:
        # 1. Achatar lista de parentes numa string legível
        familia_str = ""
        membros_demais = cad.composicao_familiar.get("demais", [])
        if membros_demais:
            lista_membros = [f"{m.get('nome','')} ({m.get('parentesco','')}) - Nasc: {m.get('nascimento','')}" for m in membros_demais]
            familia_str = " | ".join(lista_membros)
            
        # 2. Achatar as caixas de verificação (checkboxes) de infraestrutura numa string
        infra = cad.propriedade.get("infraestrutura", {})
        infra_lista = []
        if infra.get("energia"): infra_lista.append("Energia Elétrica")
        if infra.get("agua"): infra_lista.append("Água")
        if infra.get("internet"): infra_lista.append("Internet")
        if infra.get("veiculo"): infra_lista.append("Veículo Próprio")
        infra_str = ", ".join(infra_lista)

        # 3. Tratamento de campos opcionais para evitar erros se estiverem vazios
        api = cad.apicultura or {}
        man = cad.mandiocultura or {}
        hist = cad.historico or {}
        
        hist_2024 = f"Prod: {hist.get('ano2024', {}).get('prod', '')} Kg | R$ {hist.get('ano2024', {}).get('val', '')}"
        hist_2025 = f"Prod: {hist.get('ano2025', {}).get('prod', '')} Kg | R$ {hist.get('ano2025', {}).get('val', '')}"
        hist_2026 = f"Prod: {hist.get('ano2026', {}).get('prod', '')} Kg | R$ {hist.get('ano2026', {}).get('val', '')}"

        # MAPEAR TODAS AS 46 COLUNAS DAS 7 ETAPAS
        linha = [
            cad.id,                                              # 1. ID Único
            user_email,                                          # 2. Email do Agente
            cad.data_cadastro,                                   # 3. Data Cadastro
            cad.identificacao.get("nome", ""),                   # 4. Nome
            cad.identificacao.get("cpf", ""),                    # 5. CPF
            cad.identificacao.get("rg", ""),                     # 6. RG
            cad.identificacao.get("nascimento", ""),             # 7. Data de Nascimento
            cad.identificacao.get("nacionalidade", ""),          # 8. Nacionalidade
            cad.identificacao.get("genero", ""),                 # 9. Género
            cad.identificacao.get("estado_civil", ""),           # 10. Estado Civil
            cad.identificacao.get("escolaridade", ""),           # 11. Escolaridade
            cad.identificacao.get("caf_dap", ""),                # 12. CAF/DAP
            cad.identificacao.get("associacao", ""),             # 13. Associação/Cooperativa
            cad.composicao_familiar.get("conjuge", {}).get("nome", ""), # 14. Nome Cônjuge
            cad.composicao_familiar.get("conjuge", {}).get("cpf", ""),  # 15. CPF Cônjuge
            familia_str,                                         # 16. Outros Componentes Familiares
            cad.economia.get("fontes", ""),                      # 17. Fontes de Renda
            cad.economia.get("faixa", ""),                       # 18. Faixa de Renda Mensal
            cad.economia.get("cadunico", ""),                    # 19. CadÚnico
            cad.economia.get("beneficios", ""),                  # 20. Benefícios do Governo
            cad.propriedade.get("nome", ""),                     # 21. Nome da Propriedade
            cad.propriedade.get("endereco", ""),                 # 22. Endereço/Comunidade
            cad.propriedade.get("situacao", ""),                 # 23. Situação da Terra
            cad.propriedade.get("docs", ""),                     # 24. Documentos da Terra
            infra_str,                                           # 25. Infraestrutura
            cad.foco_produtivo.upper(),                          # 26. Foco Principal
            api.get("area", ""),                                 # 27. [MEL] Área (ha)
            api.get("colmeias_inst", ""),                        # 28. [MEL] Colmeias Instaladas
            api.get("colmeias_prod", ""),                        # 29. [MEL] Colmeias Produtivas
            api.get("prod_ano", ""),                             # 30. [MEL] Produção Anual (Kg)
            api.get("estrutura", ""),                            # 31. [MEL] Possui Casa de Mel
            api.get("registro", ""),                             # 32. [MEL] Registo Sanitário
            api.get("destino", ""),                              # 33. [MEL] Destino da Produção
            man.get("area_plan", ""),                            # 34. [MANDIOCA] Área Plantada
            man.get("area_colh", ""),                            # 35. [MANDIOCA] Área Colhida
            man.get("prod_ton", ""),                             # 36. [MANDIOCA] Produção Anual (Ton)
            man.get("casa_far", ""),                             # 37. [MANDIOCA] Casa de Farinha
            man.get("far_mes", ""),                              # 38. [MANDIOCA] Farinha/Mês (Kg)
            man.get("destino", ""),                              # 39. [MANDIOCA] Destino da Produção
            cad.demandas.get("dificuldades", ""),                # 40. Dificuldades Principais
            cad.demandas.get("ass_tec", ""),                     # 41. Recebe Assistência Técnica
            cad.demandas.get("producao_precisa", ""),            # 42. O que precisa para produzir mais
            cad.demandas.get("qualidade_precisa", ""),           # 43. Como melhorar a qualidade
            hist_2024,                                           # 44. Histórico 2024
            hist_2025,                                           # 45. Histórico 2025
            hist_2026                                            # 46. Histórico 2026 (Previsto)
        ]

        # LÓGICA ANTI-DUPLICAÇÃO (UPSERT)
        if cad.id in coluna_ids:
            # 1. Se o ID já existir, atualizamos a linha existente
            linha_idx = coluna_ids.index(cad.id) + 1 # +1 porque a folha de cálculo começa na linha 1
            
            aba_cadastros.update(
                values=[linha],
                range_name=f"A{linha_idx}:AT{linha_idx}", # AT é a 46ª coluna
                value_input_option='USER_ENTERED'
            )
            registros_atualizados += 1
        else:
            # 2. Se o ID não existir, guardamos para inserir no final
            linhas_para_inserir.append(linha)
            # Adiciona o ID à lista em memória para evitar duas inserções repetidas na mesma sincronização
            coluna_ids.append(cad.id) 

    # INSERE OS REGISTOS NOVOS DE UMA VEZ SÓ
    if linhas_para_inserir:
        try:
            # Insere em lote e FORÇA o início exato na Coluna A e criação de uma nova linha
            aba_cadastros.append_rows(
                linhas_para_inserir, 
                value_input_option='USER_ENTERED',
                insert_data_option='INSERT_ROWS',
                table_range='A1'
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    total = registros_atualizados + len(linhas_para_inserir)
    if total > 0:
        return {"message": f"{len(linhas_para_inserir)} inseridos e {registros_atualizados} atualizados com sucesso."}
    else:
        return {"message": "Nenhum registo válido processado."}

@app.get("/api/dashboard")
async def get_dashboard_data():
    """
    Lê todos os dados da planilha e envia para o Dashboard Analítico
    """
    if not aba_cadastros:
        raise HTTPException(status_code=500, detail="Google Sheets não configurado.")
    
    try:
        # Puxa todos os valores da planilha de uma só vez (muito rápido)
        rows = aba_cadastros.get_all_values()
        
        # Se só tiver o cabeçalho ou estiver vazia
        if not rows or len(rows) <= 1:
            return {"data": []}
            
        # Retorna todos os dados, ignorando a primeira linha (cabeçalho)
        return {"data": rows[1:]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler planilha: {str(e)}")
        
@app.delete("/api/cadastros/{record_id}")
async def delete_cadastro(record_id: str, user_email: str = Depends(verify_google_token)):
    """
    Exclui a linha correspondente no Google Sheets.
    """
    if not aba_cadastros:
        raise HTTPException(status_code=500, detail="Google Sheets não configurado.")
        
    try:
        coluna_ids = aba_cadastros.col_values(1)
        if record_id in coluna_ids:
            linha_idx = coluna_ids.index(record_id) + 1 
            
            # Verifica se o agente é o proprietário do registo (Coluna 2)
            agente_da_linha = aba_cadastros.cell(linha_idx, 2).value
            if agente_da_linha == user_email:
                aba_cadastros.delete_rows(linha_idx)
                return {"message": "Registo excluído com sucesso."}
            else:
                raise HTTPException(status_code=403, detail="Não autorizado a apagar este registo.")
        else:
            raise HTTPException(status_code=404, detail="Registo não encontrado.")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    # Executa o servidor localmente na porta 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)