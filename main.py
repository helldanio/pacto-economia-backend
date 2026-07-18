import os
import json
from fastapi import FastAPI, HTTPException, Depends, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2 import id_token
from google.auth.transport import requests

# --- CONFIGURAÇÕES GERAIS ---
app = FastAPI(title="API Pacto pela Economia")

# Permite que o frontend (celular/navegador) converse com esta API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# LISTA DE CHAVES GOOGLE: A API aceita tokens tanto do App quanto do Dashboard
GOOGLE_CLIENT_IDS = [
    "762254097331-d10m55qm8aj9pcb0gb3l93l17rorcki2.apps.googleusercontent.com", # Chave do PWA App
    "559545091323-3km4t2f24l647kmv84bmpkorjhjpm7j0.apps.googleusercontent.com"  # Nova Chave do Dashboard
]

# LISTA VIP: E-mails autorizados a gerar o Relatório PDF no Dashboard
# Coloque os e-mails da sua equipe aqui (sempre em letras minúsculas)
EMAILS_AUTORIZADOS_PDF = [
    "helldanio@gmail.com",
    "michellysamia0210@gmail.com",
    "lucilandiasousa383@gmail.com",
    "secretariaagriculturasaojose@gmail.com",
    "rubensbarbosa4@gmail.com",
    "leilanogueira3@gmail.com",
    "samuelpontesdonascimento@gmail.com", # Corrigido para minúsculo
    "guedesafilho@gmail.com"
]

try:
    # Utiliza o arquivo de credenciais do Google Cloud
    # IMPORTANTE: Garanta que o arquivo credentials.json está na mesma pasta
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    
    # ID DA PLANILHA OFICIAL
    PLANILHA_ID = "1cB0lfgN7LGCTB9aXGIsud-HPJ-hBevB1W1gtPeLJG_s"
    
    planilha = client.open_by_key(PLANILHA_ID)
    aba_cadastros = planilha.sheet1
    print("Conexão com Google Sheets estabelecida com sucesso!")
except Exception as e:
    print(f"Erro Crítico ao conectar com Google Sheets: {e}")
    aba_cadastros = None


async def verify_google_token(authorization: str = Header(None)):
    """
    Verifica a identidade do usuário.
    Aceita Tokens JWT Oficiais do Google (App e Dashboard) e Tokens de Bypass (Offline).
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Token de segurança ausente")
    
    token = authorization.replace("Bearer ", "")
    
    # Bypass 1: Modo Manual (Offline)
    if token.startswith("manual_"):
        return token.replace("manual_", "")
        
    # Bypass 2: Modo Simulado (Testes)
    if token == "mock_token":
        return "agente@teste.com"
        
    # Validação Real no Google
    try:
        # Pede para a biblioteca do Google verificar a assinatura do token
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), audience=None)
        
        # Verifica se o Token foi gerado pelo PWA App ou pelo Dashboard
        if idinfo['aud'] not in GOOGLE_CLIENT_IDS:
            raise ValueError("Token não pertence aos aplicativos autorizados.")
            
        return idinfo['email']
    except ValueError:
        raise HTTPException(status_code=401, detail="Token do Google inválido ou expirado. Faça login novamente.")


@app.get("/api/dashboard")
async def get_dashboard_data(user_email: str = Depends(verify_google_token)):
    """
    Puxa todos os dados da planilha para exibir no Painel Analítico.
    Valida se o usuário tem permissão VIP para ver o botão do PDF.
    """
    if not aba_cadastros:
        raise HTTPException(status_code=500, detail="Google Sheets não configurado no servidor.")
    
    try:
        # Puxa toda a matriz de dados da planilha de uma vez só
        rows = aba_cadastros.get_all_values()
        
        # Confere se o e-mail que requisitou está na nossa Lista VIP
        tem_permissao_pdf = user_email.lower() in [e.lower() for e in EMAILS_AUTORIZADOS_PDF]
        
        # Se estiver vazia (só cabeçalho)
        if not rows or len(rows) <= 1:
            return {"data": [], "is_admin": tem_permissao_pdf}
            
        return {"data": rows[1:], "is_admin": tem_permissao_pdf}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler planilha: {str(e)}")


@app.post("/api/cadastros/sync")
async def sync_cadastros(cadastros: list = Body(...), user_email: str = Depends(verify_google_token)):
    """
    Recebe os cadastros do aplicativo em formato JSON, trata e mapeia em 54 colunas (A a BB).
    """
    if not aba_cadastros:
        raise HTTPException(status_code=500, detail="Google Sheets não configurado.")
        
    if not cadastros:
        return {"message": "Nenhum cadastro recebido para sincronizar."}
        
    try:
        existing_data = aba_cadastros.get_all_values()
        next_row = len(existing_data) + 1
        
        rows_to_insert = []
        for c in cadastros:
            
            # Tratamento da Infraestrutura (Transforma booleanos em Texto separado por vírgula)
            infra = c.get("propriedade", {}).get("infraestrutura", {})
            infra_list = []
            if infra.get("energia"): infra_list.append("Energia Elétrica")
            if infra.get("agua"): infra_list.append("Água")
            if infra.get("internet"): infra_list.append("Internet")
            if infra.get("veiculo"): infra_list.append("Veículo Próprio")
            infra_str = ", ".join(infra_list)
            
            # Tratamento da Composição Familiar (Transforma array em Texto)
            demais = c.get("composicao_familiar", {}).get("demais", [])
            demais_list = [f"{d.get('nome', '')} ({d.get('parentesco', '')}) - {d.get('nascimento', '')}" for d in demais]
            demais_str = " | ".join(demais_list)
            
            # Tratamento dos Históricos de Produção
            h24 = c.get('historico', {}).get('ano2024', {})
            hist_2024 = f"{h24.get('prod', '')} Kg / R$ {h24.get('val', '')}" if h24.get('prod') or h24.get('val') else ""
            
            h25 = c.get('historico', {}).get('ano2025', {})
            hist_2025 = f"{h25.get('prod', '')} Kg / R$ {h25.get('val', '')}" if h25.get('prod') or h25.get('val') else ""
            
            h26 = c.get('historico', {}).get('ano2026', {})
            hist_2026 = f"{h26.get('prod', '')} Kg / R$ {h26.get('val', '')}" if h26.get('prod') or h26.get('val') else ""

            # MAPEAMENTO EXATO: 54 Colunas (Alinhado com a Planilha Oficial)
            row = [
                str(c.get("id", "")), # A (1)
                user_email,           # B (2)
                c.get("data_cadastro", ""), # C (3)
                c.get("identificacao", {}).get("nome", ""), # D (4)
                c.get("identificacao", {}).get("cpf", ""), # E (5)
                c.get("identificacao", {}).get("rg", ""), # F (6)
                c.get("identificacao", {}).get("nascimento", ""), # G (7)
                c.get("identificacao", {}).get("nacionalidade", ""), # H (8)
                c.get("identificacao", {}).get("genero", ""), # I (9)
                c.get("identificacao", {}).get("estado_civil", ""), # J (10)
                c.get("identificacao", {}).get("escolaridade", ""), # K (11)
                c.get("identificacao", {}).get("caf_dap", ""), # L (12)
                c.get("identificacao", {}).get("associacao", ""), # M (13)
                c.get("composicao_familiar", {}).get("conjuge", {}).get("nome", ""), # N (14)
                c.get("composicao_familiar", {}).get("conjuge", {}).get("cpf", ""), # O (15)
                demais_str, # P (16)
                c.get("economia", {}).get("fontes", ""), # Q (17)
                c.get("economia", {}).get("faixa", ""), # R (18)
                c.get("economia", {}).get("cadunico", ""), # S (19)
                c.get("economia", {}).get("beneficios", ""), # T (20)
                c.get("propriedade", {}).get("nome", ""), # U (21)
                c.get("propriedade", {}).get("endereco", ""), # V (22)
                c.get("propriedade", {}).get("situacao", ""), # W (23)
                c.get("propriedade", {}).get("docs", ""), # X (24)
                infra_str, # Y (25)
                c.get("foco_produtivo", ""), # Z (26)
                c.get("apicultura", {}).get("area", ""), # AA (27)
                c.get("apicultura", {}).get("colmeias_inst", ""), # AB (28)
                c.get("apicultura", {}).get("colmeias_prod", ""), # AC (29)
                c.get("apicultura", {}).get("prod_ano", ""), # AD (30)
                c.get("apicultura", {}).get("estrutura", ""), # AE (31)
                c.get("apicultura", {}).get("registro", ""), # AF (32)
                c.get("apicultura", {}).get("destino", ""), # AG (33)
                c.get("mandiocultura", {}).get("area_plan", ""), # AH (34)
                c.get("mandiocultura", {}).get("area_colh", ""), # AI (35)
                c.get("mandiocultura", {}).get("prod_ton", ""), # AJ (36)
                c.get("mandiocultura", {}).get("casa_far", ""), # AK (37)
                c.get("mandiocultura", {}).get("far_mes", ""), # AL (38)
                c.get("mandiocultura", {}).get("destino", ""), # AM (39)
                c.get("demandas", {}).get("dificuldades", ""), # AN (40)
                c.get("demandas", {}).get("ass_tec", ""), # AO (41)
                c.get("demandas", {}).get("producao_precisa", ""), # AP (42)
                c.get("demandas", {}).get("qualidade_precisa", ""), # AQ (43)
                hist_2024, # AR (44)
                hist_2025, # AS (45)
                hist_2026, # AT (46)
                c.get("observacoes", ""), # AU (47)
                c.get("cajucultura", {}).get("area", ""), # AV (48)
                c.get("cajucultura", {}).get("prod_ano", ""), # AW (49)
                c.get("cajucultura", {}).get("destino", ""), # AX (50)
                c.get("outras_culturas", {}).get("descricao", ""), # AY (51)
                c.get("outras_culturas", {}).get("area", ""), # AZ (52)
                c.get("outras_culturas", {}).get("prod_ano", ""), # BA (53)
                c.get("outras_culturas", {}).get("destino", ""), # BB (54)
            ]
            rows_to_insert.append(row)
        
        # Insere em lote (Batch Insert)
        if rows_to_insert:
            end_row = next_row + len(rows_to_insert) - 1
            range_name = f"A{next_row}:BB{end_row}"
            aba_cadastros.update(range_name, rows_to_insert)
            
        return {"status": "success", "message": f"{len(rows_to_insert)} cadastros sincronizados com sucesso."}
        
    except Exception as e:
        # Repassa o erro detalhado para o frontend se houver falha (ex: Colunas incompatíveis)
        raise HTTPException(status_code=400, detail=f"Erro ao escrever na planilha: {str(e)}")


@app.delete("/api/cadastros/{cadastro_id}")
async def delete_cadastro(cadastro_id: str, user_email: str = Depends(verify_google_token)):
    """
    Busca a linha na planilha através da Coluna 1 (ID Unico) e apaga a linha inteira.
    """
    if not aba_cadastros:
        raise HTTPException(status_code=500, detail="Google Sheets não configurado.")
        
    try:
        # Traz todos os IDs da primeira coluna para procurar onde está
        col_ids = aba_cadastros.col_values(1)
        
        try:
            # +1 porque as planilhas do Google começam no índice 1 (não 0)
            row_index = col_ids.index(str(cadastro_id)) + 1
        except ValueError:
            raise HTTPException(status_code=404, detail="Cadastro não encontrado na planilha oficial")
        
        # Executa a exclusão da linha
        aba_cadastros.delete_rows(row_index)
        return {"status": "success", "message": "Registro excluído permanentemente da planilha."}
        
    except HTTPException:
        raise # Repassa o Erro 404 normalmente
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))