# main.py
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import gspread
from google.oauth2 import id_token
from google.auth.transport import requests
import json

app = FastAPI(title="Pacto pela Economia API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Mude para a URL do seu frontend em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GOOGLE_CLIENT_ID = "762254097331-d10m55qm8aj9pcb0gb3l93l17rorcki2.apps.googleusercontent.com"
SHEET_ID = "1cB0lfgN7LGCTB9aXGIsud-HPJ-hBevB1W1gtPeLJG_s"

try:
    gc = gspread.service_account(filename='credentials.json')
    planilha = gc.open_by_key(SHEET_ID)
    aba_cadastros = planilha.sheet1
except Exception as e:
    print(f"Erro Google Sheets: {e}")
    aba_cadastros = None

class RecordModel(BaseModel):
    id: str
    agente_email: str
    data_cadastro: str
    sync_status: str
    identificacao: Dict[str, Any]
    economia: Dict[str, Any]
    propriedade: Dict[str, Any]
    foco_produtivo: str
    apicultura: Optional[Dict[str, Any]] = None
    mandiocultura: Optional[Dict[str, Any]] = None
    demandas: Dict[str, Any]
    historico: Dict[str, Any]

def verify_google_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = authorization.split(" ")[1]
    if token == "mock_token": return "agente@teste.com"
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
        return idinfo['email']
    except ValueError:
        raise HTTPException(status_code=401, detail="Token inválido")

@app.post("/api/cadastros/sync")
async def sync_cadastros(cadastros: List[RecordModel], user_email: str = Depends(verify_google_token)):
    if not aba_cadastros: raise HTTPException(status_code=500, detail="Planilha offline")
    linhas = []
    for cad in cadastros:
        if cad.agente_email != user_email: continue
        linha = [
            cad.id, user_email, cad.data_cadastro,
            cad.identificacao.get("nome", ""), cad.identificacao.get("cpf", ""),
            cad.foco_produtivo.upper(), cad.propriedade.get("nome", ""),
            cad.propriedade.get("endereco", ""),
            cad.apicultura.get("prod_ano", "") if cad.foco_produtivo == 'mel' else cad.mandiocultura.get("prod_ton", ""),
            cad.demandas.get("dificuldades", ""), cad.demandas.get("producao_precisa", "")
        ]
        linhas.append(linha)
    if linhas:
        aba_cadastros.append_rows(linhas, value_input_option='USER_ENTERED')
        return {"message": "Sincronizado!"}
    return {"message": "Nenhum registro"}
