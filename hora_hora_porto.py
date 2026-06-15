import urllib
import pandas as pd
import pyodbc
from sqlalchemy import create_engine
import streamlit as st
import datetime
import sys
import subprocess
import time

# ==============================================================================
# CONFIGURAÇÕES DA VPN FORTICLIENT
# ==============================================================================
# Ajuste o caminho do executável CLI se for diferente no seu sistema
FORTICLIENT_PATH = r"C:\Program Files\Fortinet\FortiClient\FortiSSLVPNsys.exe"
VPN_SERVER = "remoto.dnr.com.br"  # Substitua pelo IP/Domínio e porta da sua VPN
VPN_USER = "36246153860"
VPN_PASS = "Trocarsenha@@9120"         # Lembrete: Use st.secrets por segurança depois!

def conectar_vpn():
    """Dispara o comando CLI para conectar ao FortiClient"""
    comando = [
        FORTICLIENT_PATH,
        "--server", VPN_SERVER,
        "--vpnuser", VPN_USER,
        "--keepalive"
    ]
    try:
        # Iniciando o processo enviando a senha via input
        processo = subprocess.Popen(
            comando, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        # Envia a senha para o prompt do FortiClient
        processo.stdin.write(f"{VPN_PASS}\n")
        processo.stdin.flush()
        
        # Aguarda alguns segundos para a VPN estabelecer o túnel de rede
        time.sleep(8)
        return processo
    except Exception as e:
        st.error(f"Falha ao iniciar o FortiClient: {e}")
        return None

def desconectar_vpn(processo_vpn):
    """Encerra o processo da VPN de forma limpa"""
    if processo_vpn:
        processo_vpn.terminate()
        processo_vpn.wait()

# ==============================================================================
# CONFIGURAÇÕES DO BANCO DE DADOS
# ==============================================================================
server = "192.168.1.9"
username = "sidnei.soares"
password = "Trocarsenha@@5966"

if sys.platform == "win32":
    driver = "{ODBC Driver 18 for SQL Server}"
else:
    driver = "{ODBC Driver 18 for SQL Server}"

conn_str = (
    f"DRIVER={driver};SERVER={server};"
    f"UID={username};PWD={password};"
    "Encrypt=yes;TrustServerCertificate=yes;"
)

pd.set_option('display.max_columns', None)
df = None

# ==============================================================================
# EXECUÇÃO DA CONEXÃO E QUERY (Cercado pelo ciclo de vida da VPN)
# ==============================================================================
# 1. Abre a VPN antes de tocar no banco de dados
processo_ativo_vpn = conectar_vpn()

try:
    params = urllib.parse.quote_plus(conn_str)
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

    query = """
    SELECT 
        A.DATA_TABULACAO,
        A.HORA,
        A.TIPO_ACORDO,
        A.FAIXA_ATRASO_V1 AS FAIXA_ATRASO,
        A.NOME,
        A.CARTEIRA,
        A.ATUACAO,
        A.CLASSIFICACAO_NEGOCIO,
        SUM(CAST(A.ACIONAMENTO AS INT)) as ACIONAMENTO,
        SUM(CAST(A.ALO as int )) AS ALO,
        SUM(CAST(A.CPC AS int)) AS CPC,
        SUM(CAST(A.CPCA AS int)) as CPCA,
        SUM(CAST(A.ACORDO AS int)) AS ACORDO,
        SUM(A.VALOR_PARCELA) AS VALOR_PARCELA,
        SUM(A.RISCO) AS VALOR_RISCO
    FROM MIS..ANALITICO_HORA_HORA_PORTO A
    GROUP BY 
        A.DATA_TABULACAO,
        A.HORA,
        A.TIPO_ACORDO,
        A.FAIXA_ATRASO_V1,
        A.NOME,
        A.CARTEIRA,
        A.ATUACAO,
        A.CLASSIFICACAO_NEGOCIO
    """

    # Lendo os dados do banco enquanto a VPN está ativa
    df = pd.read_sql(query, engine)

except Exception as e:
    st.error(f"Erro ao processar a tabela no banco: {e}")

finally:
    # 2. Garante que a VPN será fechada mesmo se a query falhar
    desconectar_vpn(processo_ativo_vpn)


# ==============================================================================
# TRATAMENTO DE DADOS E RENDERIZAÇÃO INTERFACE
# ==============================================================================
if df is not None:
    # Converte a coluna original para datetime para o funcionamento do calendário
    df['DATA_TABULACAO_DT'] = pd.to_datetime(df['DATA_TABULACAO']).dt.date
    
    # PAINÉIS DE FILTROS NA BARRA LATERAL (SIDEBAR)
    st.sidebar.header("Filtros do Relatório")
    
    # 1. Filtro de Data
    data_maxima = df['DATA_TABULACAO_DT'].max() if not df.empty else datetime.date.today()
    data_selecionada = st.sidebar.date_input("Selecione a Data", data_maxima, format="DD/MM/YYYY")
    
    # Filtra a base pela data primeiro para carregar dinamicamente as opções dos próximos filtros
    base_filtrada = df[df['DATA_TABULACAO_DT'] == data_selecionada].copy()
    
    # 2. Filtro de Carteira (Multiselect)
    opcoes_carteira = sorted(base_filtrada['CARTEIRA'].dropna().unique().tolist())
    carteiras_sel = st.sidebar.multiselect("Carteira", options=opcoes_carteira, default=opcoes_carteira)
    
    # 3. Filtro de Faixa de Atraso (Multiselect)
    opcoes_faixa = sorted(base_filtrada['FAIXA_ATRASO'].dropna().unique().tolist())
    faixas_sel = st.sidebar.multiselect("Faixa Atraso", options=opcoes_faixa, default=opcoes_faixa)
    
    # 4. Filtro de Célula / Atuação (Multiselect)
    opcoes_celula = sorted(base_filtrada['ATUACAO'].dropna().unique().tolist())
    celulas_sel = st.sidebar.multiselect("Célula", options=opcoes_celula, default=opcoes_celula)
    
    # 5. Filtro de Negócio (Multiselect)
    opcoes_negocio = sorted(base_filtrada['CLASSIFICACAO_NEGOCIO'].dropna().unique().tolist())
    negocios_sel = st.sidebar.multiselect("Classificação Negócio", options=opcoes_negocio, default=opcoes_negocio)
    
    # ----------------------------------------------------
    # APLICANDO TODOS OS FILTROS SELECIONADOS
    # ----------------------------------------------------
    df_filtrado = base_filtrada[
        (base_filtrada['CARTEIRA'].isin(carteiras_sel)) &
        (base_filtrada['FAIXA_ATRASO'].isin(faixas_sel)) &
        (base_filtrada['ATUACAO'].isin(celulas_sel)) &
        (base_filtrada['CLASSIFICACAO_NEGOCIO'].isin(negocios_sel))
    ].copy()
    # ----------------------------------------------------

    # Conversão explícita das colunas para tipo numérico
    colunas_numericas = ['ACIONAMENTO', 'ALO', 'CPC', 'CPCA', 'ACORDO', 'VALOR_PARCELA', 'VALOR_RISCO']
    df_filtrado[colunas_numericas] = df_filtrado[colunas_numericas].apply(pd.to_numeric, errors='coerce')   

    # Só monta o relatório se houver dados correspondentes após os filtros
    if not df_filtrado.empty:
        
        # Criando a tabela dinâmica base fixada apenas em HORA com a linha de TOTAL GERAL
        dinamica = pd.pivot_table(
            df_filtrado,                                 
            index='HORA',  
            values=colunas_numericas,     
            aggfunc='sum',
            margins=True,
            margins_name='TOTAL GERAL'
        )
        
        # Ordenação fixa das colunas nativas para garantir o padrão visual do relatório
        dinamica = dinamica[['ACIONAMENTO', 'ALO', 'CPC', 'CPCA', 'ACORDO', 'VALOR_PARCELA', 'VALOR_RISCO']]

        # CRIANDO AS QUATRO COLUNAS DE CÁLCULO NA TABELA DINÂMICA
        dinamica['TKM'] = dinamica['VALOR_RISCO'] / dinamica['ACORDO']
        dinamica['Alo X Acio'] = dinamica['ALO'] / dinamica['ACIONAMENTO']
        dinamica['Cpc X Alo'] = dinamica['CPC'] / dinamica['ALO']
        dinamica['Reversão'] = dinamica['ACORDO'] / dinamica['CPC']
        
        # Tratamento matemático para divisões por zero ou valores nulos gerados
        dinamica = dinamica.fillna(0).replace([float('inf'), float('-inf')], 0)

        # ----------------------------------------------------
        # FORMATANDO E EXIBINDO O RELATÓRIO DINÂMICO
        # ----------------------------------------------------
        st.subheader(f"📊 Relatório de Hora a Hora Porto Seguro — {data_selecionada.strftime('%d/%m/%Y')}")
        
        # Função lambda para formatar os valores para Moeda Brasileira (R$ 2.000,00)
        formato_moeda_br = lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        # Renderiza a tabela dinâmica principal expandida na largura total
        st.dataframe(dinamica.style.format({
            'VALOR_PARCELA': formato_moeda_br,
            'VALOR_RISCO': formato_moeda_br,
            'TKM': formato_moeda_br,
            'Alo X Acio': '{:.2%}',
            'Cpc X Alo': '{:.2%}',
            'Reversão': '{:.2%}'
        }), use_container_width=True)
        
        # ----------------------------------------------------
        # EXIBIÇÃO EXPANDIDA DO QUADRO DE DADOS BRUTOS + LINHA DE TOTAL
        # ----------------------------------------------------
        # Formata a data para texto dd/mm/aaaa nas linhas comuns
        df_filtrado['DATA_TABULACAO'] = pd.to_datetime(df_filtrado['DATA_TABULACAO']).dt.strftime('%d/%m/%Y')
        df_exibicao = df_filtrado.drop(columns=['DATA_TABULACAO_DT'])

        # Criando a linha de Total para os dados brutos
        linha_total = {col: df_exibicao[col].sum() for col in colunas_numericas}
        linha_total['DATA_TABULACAO'] = 'TOTAL GERAL'
        linha_total['HORA'] = '-'
        linha_total['TIPO_ACORDO'] = '-'
        linha_total['FAIXA_ATRASO'] = '-'
        linha_total['NOME'] = '-'
        linha_total['CARTEIRA'] = '-'
        linha_total['ATUACAO'] = '-'
        linha_total['CLASSIFICACAO_NEGOCIO'] = '-'
        
        df_total_row = pd.DataFrame([linha_total])
        df_exibicao_com_total = pd.concat([df_exibicao, df_total_row], ignore_index=True)
        
    else:
        st.warning("Não foram encontrados dados com a combinação de filtros selecionada.")