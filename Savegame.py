import numpy as np
import pandas as pd
import re
from datetime import datetime
from typing import List
import time
import os
import glob
from pymem import Pymem
from pymem.process import module_from_name

class Savegame():
    def __init__(self, caminho: str="autosave.v3") -> None:
        self.caminho = caminho

        with open(self.caminho, "r") as arquivo:
            self.conteudo = arquivo.read()

    @property
    def data(self):
        d = re.findall(r'game_date=([\d.]+)\n',
                       string=self.conteudo)[0]
        dd = datetime.strptime(d, "%Y.%m.%d")
        d = datetime.strftime(dd,
                              "%d/%m/%Y")
        return (d, dd)
    
    def extrair_paises(self):
        return self.conteudo.split('country_manager')[1].split('government_stances_for_laws')[0:-1]

    def extrair_construcoes(self):
        return self.conteudo.split('building_manager')[1].split('building_ownership_manager')[0].split('production_methods={')

    def matcher(self, x: str, 
                reg: re.Pattern, 
                grupo: int=1):
        m = reg.search(x)
        if m:
            return m.group(grupo)
        else:
            return ""
        
        
    def calcular_preco(self, df):
        # preco = (demanda-oferta)/(np.min([demanda, oferta], axis=0))
        # preco = np.clip(preco, -1, 1)
        # preco *= 0.75
        # preco += 1

        preco = (df['demanda']-df['oferta'])/(np.min([df['demanda'], df['oferta']], axis=0))
        preco = np.clip(preco, -1, 1)
        preco *= 0.75
        preco +=1

        bases = [50,60,70,80,80,70,80,20,20,20,20,30,30,30,30,30,30,30,60,70,40,40,50,30,40,40,40,40,40,60,50,40,30,40,50,70,30,30,30,50,50,50,30,40,50,100,70,80,60,60,100,200]
        df['preco'] = df['bem'].apply(lambda x: bases[x])
        df['preco'] *= preco

        bases_nome = {
            'ammunition':50,
            'small_arms':60,
            'artillery':70,
            'tanks':80,
            'aeroplanes':80,
            'manowars':70,
            'ironclads':80,
            'grain':20,
            'fish':20,
            'fabric':20,
            'wood':20,
            'groceries':30,
            'clothes':30,
            'furniture':30,
            'paper':30,
            'services':30,
            'transportation':30,
            'electricity':30,
            'clippers':60,
            'steamers':70,
            'silk':40,
            'dye':40,
            'sulfur':50,
            'coal':30,
            'iron':40,
            'lead':40,
            'hardwood':40,
            'rubber':40,
            'oil':40,
            'engines':60,
            'steel':50,
            'glass':40,
            'fertilizer':30,
            'tools':40,
            'explosives':50,
            'porcelain':70,
            'meat':30,
            'fruit':30,
            'liquor':30,
            'wine':50,
            'tea':50,
            'coffee':50,
            'sugar':30,
            'tobacco':40,
            'opium':50,
            'automobiles':100,
            'telephones':70,
            'radios':80,
            'luxury_clothes':60,
            'luxury_furniture':60,
            'gold':100,
            'fine_art':200,
        }

        

        return df
    
    def retornar_estados(self):
        h = self.extrair_paises()
        hh = pd.Series(h)

        df = hh.str.extractall(r'definition="(?P<tag>[A-Z]{3})"|states={ (?P<estados>.+?) }').groupby(level=0).first().reset_index(drop=True)
        df['estados']=df['estados'].str.split(' ')
        df = df.explode('estados', ignore_index = True)

        return df
    
    def retornar_precos(self):
        h = self.conteudo.split('current_price_report')[1].split('}')[0]
        hh = pd.Series(h)

        df = hh.str.extractall(r'(?P<produto>[\d.]+)=(?P<preco>[\d.]+)').groupby(level=1).first().reset_index(drop=True)

        df['preco'] = pd.to_numeric(df['preco'])

        return df

    def calcular_valor_por_linha(self, i, r, df, mercado_oferta, mercado_demanda, decrescer=False):
        if r['nivel_producao']==0:
                return (0, 0)
        x = df.copy()
        x.iloc[i,5:] = x.iloc[i,5:].apply(pd.to_numeric, errors="coerce")*float(1/r['nivel_producao'])

        output = x.iloc[i,:].filter(like="_producao")
        output = output.filter(regex=r"^\d")
        input = x.iloc[i,:].filter(like="_consumo")
        input = input.filter(regex=r"^\d")

        oferta = output
        oferta.index = oferta.index.str.replace("_producao","")
        oferta.name="oferta"

        demanda = input
        demanda.index = demanda.index.str.replace("_consumo","")
        demanda.name="demanda"

        oferta = oferta.reset_index()   # por enquanto essa oferta é igual a output_goods
        demanda = demanda.reset_index() # por enquanto essa oferta é igual a input_goods

        oferta = oferta.astype({
            "index":np.int32 ,
            "oferta": np.float64
        })

        demanda = demanda.astype({
            "index":np.int32 ,
            "demanda": np.float64
        })

        oferta_teste = mercado_oferta
        consumo_teste = mercado_demanda

        consumo_teste = demanda.merge(consumo_teste, on="index",how='outer').fillna(0)

        oferta_teste = oferta.merge(oferta_teste, on="index",how='outer').fillna(0)
        if decrescer:
            oferta_teste['oferta'] = oferta_teste['oferta_x']-oferta_teste['oferta_y']
            consumo_teste['demanda'] = consumo_teste['demanda_x']-consumo_teste['demanda_y']
        else:
            oferta_teste['oferta'] = oferta_teste['oferta_x']+oferta_teste['oferta_y']
            consumo_teste['demanda'] = consumo_teste['demanda_x']+consumo_teste['demanda_y']

        oferta_teste = oferta_teste[["index", "oferta"]]
        consumo_teste = consumo_teste[["index", "demanda"]]



        mercado = oferta_teste.merge(consumo_teste, how='inner').fillna(0).set_index("index")



        precos_novo = self.calcular_preco(mercado)

        if not decrescer:
            x.iloc[i,5:] = x.iloc[i,5:].apply(pd.to_numeric, errors="coerce")*float(r['nivel_producao']+1)
        else:
            x.iloc[i,5:] = x.iloc[i,5:].apply(pd.to_numeric, errors="coerce")*float(r['nivel_producao']-1)

        output = x.iloc[:,:].filter(like="_producao")
        output = output.filter(regex=r"^\d")
        input = x.iloc[:,:].filter(like="_consumo")
        input = input.filter(regex=r"^\d")

        oferta = output
        oferta.columns = oferta.columns.str.replace("_producao","")
        oferta = oferta.sum()
        oferta.name="oferta"
        oferta =  oferta.reset_index()

        demanda = input
        demanda.columns = demanda.columns.str.replace("_consumo","")
        demanda = demanda.sum()
        demanda.name="demanda"
        demanda = demanda.reset_index()

        mercado = oferta.merge(demanda, on="index", how='outer').fillna(0)

        mercado['valor_agregado'] = mercado['oferta']-mercado['demanda']

        valor_agregado = mercado[['index', 'valor_agregado']]
        valor_agregado = valor_agregado.astype({
            "index":np.int32
        })

        valor_agregado =  valor_agregado.merge(precos_novo)

        valor_agregado = valor_agregado['preco']*valor_agregado['valor_agregado']

        va_estimado = float(np.sum(valor_agregado))

        key = str(r['id_producao'])

        return (key, va_estimado)


    def calcular_valor_agregado(self, df, precos=pd.DataFrame):
        oferta = df.filter(like="_producao").filter(regex=r'^\d')
        demanda = df.filter(like="_consumo").filter(regex=r'^\d')

        oferta.columns = oferta.columns.str.replace("_producao","")
        demanda.columns = demanda.columns.str.replace("_consumo","")

        oferta = oferta.sum().reset_index()
        demanda = demanda.sum().reset_index()

        mercado = oferta.merge(demanda, on="index", how="outer").fillna(0).set_index("index")
        mercado=mercado.rename(columns={"0_x":"oferta","0_y":"demanda"})
        if precos.empty:
            precos_novo = self.calcular_preco(mercado)
        else:
            precos_novo = precos

        mercado = mercado.reset_index()
        mercado['index'] = mercado['index'].astype(np.int32)

        mercado = mercado.merge(precos_novo, on="index", how="outer").fillna(0)

        mercado['valor_agregado'] = (mercado['oferta']-mercado['demanda'])*mercado['preco']

        va_atual = mercado['valor_agregado'].sum()

        return va_atual
    

    def calcular_valor_mercado_atual(self, oferta, demanda):

        return 1


    def calcular_expansao(self, df, decrescer=False):

        x = df.copy()

        ids_df = []
        vas_df = []

        
        mercado_oferta, mercado_demanda = self.escrever_mercado_atual()
        mercado = mercado_oferta.merge(mercado_demanda, on="index").set_index("index")
        precos = self.calcular_preco(mercado)

        va_atual = self.calcular_valor_agregado(df, precos=precos)
        



        for i, r in x.iterrows():
            a = self.calcular_valor_por_linha(i, r, x, mercado_oferta, mercado_demanda, decrescer=decrescer)

            ids_df.append(a[0])
            vas_df.append(a[1]-va_atual)

        dados = pd.DataFrame({"id":ids_df, "va_estimado":vas_df})

        return dados

    def calcular_preco(self, df):
        #
        # Dê um df com index igual ao id do bem, uma coluna oferta e outra demanda


        # preco = (demanda-oferta)/(np.min([demanda, oferta], axis=0))
        # preco = np.clip(preco, -1, 1)
        # preco *= 0.75
        # preco += 1


        preco = (df['demanda']-df['oferta'])/(np.min([df['demanda'], df['oferta']], axis=0))
        preco = np.clip(preco, -1, 1)
        preco *= 0.75
        preco +=1
        preco = preco.fillna(0)
        preco = preco.reset_index()
        preco['index']=pd.to_numeric(preco['index'])

        bases = pd.DataFrame(np.array([50,60,70,80,80,70,80,20,20,20,20,30,30,30,30,30,30,30,60,70,40,40,50,30,40,40,40,40,40,60,50,40,30,40,50,70,30,30,30,50,50,50,30,40,50,100,70,80,60,60,100,200]).reshape(-1, 1))
        bases["index"] = pd.to_numeric(bases.index)

        

        preco = preco.merge(bases, on="index")
        preco['preco'] = preco['0_x']*preco['0_y']

        precos = preco[["index", "preco"]]

        return precos
    
    def escrever_mercado_atual(self):
        pm = Pymem("victoria3.exe")
        module = module_from_name(pm.process_handle, "victoria3.exe")
        base_address = module.lpBaseOfDll

        CMarket_base = pm.read_longlong(pm.read_longlong(pm.read_longlong(base_address+0x045AF920)+0x20)+0x3d8)

        quantidadeBens = pm.read_int(CMarket_base+0x22c)

        df_oferta = {
            "index":[],
            "oferta":[]
        }

        df_consumo = {
            "index":[],
            "demanda":[]
        }

        for i in range(quantidadeBens):
            try:
                indexBens = pm.read_longlong(CMarket_base+0x258) + i*0x18 + 0x8
                valido = int.from_bytes(pm.read_bytes(indexBens+0x4,1))
                quantidadeProduzida = pm.read_longlong(indexBens+0x8)/100000
                idBem = pm.read_int(pm.read_longlong(indexBens)+0x10)
                df_oferta["index"].append(idBem)
                df_oferta["oferta"].append(quantidadeProduzida)

                indexBens = pm.read_longlong(CMarket_base+0x220) + i*0x18 + 0x8
                valido = int.from_bytes(pm.read_bytes(indexBens+0x4,1))
                quantidadeProduzida = pm.read_longlong(indexBens+0x8)/100000
                idBem = pm.read_int(pm.read_longlong(indexBens)+0x10)
                df_consumo["index"].append(idBem)
                df_consumo["demanda"].append(quantidadeProduzida)
            except:
                continue

        df_consumo = pd.DataFrame(df_consumo)
        df_consumo = df_consumo.astype({
            "index":np.int32 ,
            "demanda": np.float64
        })
        df_oferta = pd.DataFrame(df_oferta)
        df_oferta = df_oferta.astype({
            "index":np.int32,
            "oferta": np.float64
        })

        return(df_oferta, df_consumo)
    
    def apply_calculo(self , row, df):
        x = df.copy()

        a = self.calcular_valor_por_linha(row.name, row, x)

        return a[1]

        # ids_df = []
        # vas_df = []

        # for i, r in x.iterrows():
        #     a = self.calcular_valor_por_linha(i, r, x)

        #     ids_df.append(a[0])
        #     vas_df.append(a[1])

        #     dados = pd.DataFrame({"id":ids_df, "va_estimado":vas_df})

        # return dados

    def analise_bens(self, decrescer=False):
        h = self.extrair_construcoes()
        hh = pd.Series(h)

        ids_building = hh.str.extractall(r'\n(?P<id>\d+)={|levels=(?P<nivel>\d+)|state=(?P<estado>\d+)|building=(?P<tipo>[\w_]+)|staffing=(?P<ocupacao>[\d.]+)').groupby(level=0).first()
        ids_building['ocupacao'] = pd.to_numeric(ids_building['ocupacao'])/pd.to_numeric(ids_building['nivel'])

        bens_produzidos_temp = hh.str.split('output_goods').str[1].str.split('}').str[0].str.extractall(r'(?P<bem_produzido>[\d.]+)=(?P<quantidade_produzida>[\d.]+)')

        matriz_produzidos = bens_produzidos_temp.pivot_table(
                                columns="bem_produzido",
                                values="quantidade_produzida",
                                aggfunc='first',
                                index=bens_produzidos_temp.index.get_level_values(0)
                            ).fillna(0)
        matriz_produzidos = matriz_produzidos.reindex(columns=sorted(matriz_produzidos, key=int))
        matriz_produzidos = ids_building.join(matriz_produzidos).fillna(0)
        matriz_produzidos = matriz_produzidos.apply(pd.to_numeric, errors='coerce').reset_index(drop=True)


        bens_consumidos_temp = hh.str.split('input_goods').str[1].str.split('}').str[0].str.extractall(r'(?P<bem_consumido>[\d.]+)=(?P<quantidade_consumida>[\d.]+)')

        matriz_consumidos = bens_consumidos_temp.pivot_table(
                                columns="bem_consumido",
                                values="quantidade_consumida",
                                aggfunc='first',
                                index=bens_consumidos_temp.index.get_level_values(0)
                            ).fillna(0)
        matriz_consumidos = matriz_consumidos.reindex(columns=sorted(matriz_consumidos, key=int))
        matriz_consumidos = ids_building.join(matriz_consumidos).fillna(0)
        matriz_consumidos = matriz_consumidos.apply(pd.to_numeric, errors='coerce').reset_index(drop=True)

        df_estados = self.retornar_estados()

        df_estados['estados'] = pd.to_numeric(df_estados['estados'])

        consumo = df_estados.merge(right=matriz_consumidos, left_on="estados", right_on="estado")

        producao = df_estados.merge(right=matriz_produzidos, left_on="estados", right_on="estado")

        precos = self.retornar_precos()

        ######### testar expansão ###############

        producao_brasil = producao.loc[producao['tag']=="BRZ",:].add_suffix("_producao")

        consumo_brasil = consumo.loc[consumo['tag']=="BRZ",:].add_suffix("_consumo")

        df = producao_brasil.merge(right=consumo_brasil, left_on="id_producao", right_on="id_consumo", how="outer").fillna(0)
        df = df.drop(['tag_consumo', 'estados_consumo', 'nivel_consumo','estado_consumo', 'id_consumo'], axis=1)

        print("\nCalculando expansão...")

        resultado = self.calcular_expansao(df, decrescer=decrescer)
        # resultado = df.apply(self.apply_calculo, args=(df,), axis=1)

        estados_nomes = self.retornar_nomes_estados()

        resultado = resultado.merge(ids_building, how="inner")
        resultado['va_estimado'] = resultado['va_estimado']*resultado['ocupacao']**3
        resultado = resultado.sort_values(by="va_estimado", ascending=False)
        resultado = resultado.groupby('tipo').head(3)
        resultado = resultado.merge(estados_nomes)
        print()
        print(resultado)

    def retornar_nomes_estados(self):
        h = self.conteudo.split('\nstates={\n')[1].split('interest_groups')[0].split('pop_statistics')
        hh = pd.Series(h)
        return hh.str.extractall(r'\n(?P<estado>\d+)={|region="(?P<estadoNome>[\w_]+)"').groupby(level=0).first().reset_index(drop=True)

    
    def calcular_melhores_construcoes(self):
        h = self.extrair_construcoes()
        hh = pd.Series(h)

        r = self.conteudo.split('player_manager')[1].split('sways')[0]
        id_pais = int(re.findall(r'country=(\d+)', r)[0])
        tag_pais = re.findall(r'definition="([A-Z]{3})"',self.conteudo.split(str(id_pais)+"={\n\tis_main_tag")[1].split('infamy')[0])[0]

        r = self.conteudo.split('current_price_report')[1].split('pop_income_from_diplomacy')[0]
        precos = [float(x) for x in re.findall(r'[\d.]+=(?P<preco>[\d.]+)', r)]

        r = self.conteudo.split('spending_variables={\n\t\t\tcountry='+str(id_pais))[1].split('goods_production')[0]
        impostos_consumo = [float(x) for x in re.findall(r'potential_consumption_taxes={ (.+?) }',r)[0].split(' ')]

        taxas = {
            "very_low":0.2,
            "low":0.275,
            "medium":0.35,
            "high":0.425,
            "very_high":0.5
        }

        taxa_pais = taxas[re.findall(r'tax_level=([a-z_]+)',self.conteudo.split(str(id_pais)+'={\n\tis_main_tag=yes')[1].split('country_type="')[0])[0]]

        quantidade_pop = [x/taxa_pais for x in impostos_consumo]

        quantidade_pop = [a/b for a,b in zip(quantidade_pop, precos)]





        regexs = [
            r'\n(?P<id>\d+)={\n',
            r'levels=(?P<nivel>\d+)',
            r'state=(?P<estado>\d+)',
            r'building=(?P<tipo>[\w_]+)',
            # r'goods_cost=(?P<custo_bens>[\d.]+)',
            # r'goods_sales=(?P<receita_bens>[\d.]+)',
            # r'cash_reserves=(?P<reservas>[\d.]+)',
            r'staffing=(?P<ocupacao>[\d.]+)',
            r'input_goods={(?P<input_goods>[\s\S]+?)}',
            r'output_goods={(?P<output_goods>[\s\S]+?)}'



        ]

        df = pd.DataFrame(hh.str.extractall(r'|'.join(regexs)).groupby(level=0).first())
        df['id'] = pd.to_numeric(df['id'])
        df['estado'] = pd.to_numeric(df['estado'])

        oferta = df['output_goods'].str.extractall(r'(?P<bem>[\d.]+)=(?P<quantidade>[\d.]+)').reset_index().rename(columns={"level_0":"id"})
        demanda = df['input_goods'].str.extractall(r'(?P<bem>[\d.]+)=(?P<quantidade>[\d.]+)').reset_index().rename(columns={"level_0":"id"})
        oferta[['id', 'bem', 'quantidade']] = oferta[['id', 'bem', 'quantidade']].apply(pd.to_numeric)
        demanda[['id', 'bem', 'quantidade']] = demanda[['id', 'bem', 'quantidade']].apply(pd.to_numeric)

        oferta = oferta.merge(right=df[['id','estado', 'tipo']]).drop(columns=['match'])
        demanda = demanda.merge(right=df[['id','estado']]).drop(columns=['match'])

        paises = self.retornar_pibs()
        paises['estados'] = pd.to_numeric(paises['estados'])

        oferta = oferta.merge(paises, left_on="estado", right_on="estados")
        demanda = demanda.merge(paises, left_on="estado", right_on="estados")

        oferta_pais = oferta.groupby(['tag', 'bem'])['quantidade'].agg(oferta='sum').reset_index()
        demanda_pais = demanda.groupby(['tag', 'bem'])['quantidade'].agg(demanda='sum').reset_index()

        oferta_pais = oferta_pais[oferta_pais['tag']==tag_pais]
        demanda_pais = demanda_pais[demanda_pais['tag']==tag_pais]

        demanda_pais['quantidade_pop'] = demanda_pais['bem'].apply(lambda x: quantidade_pop[x])

        demanda_pais['demanda'] += demanda_pais['quantidade_pop']
        demanda_pais=demanda_pais.drop(columns=['quantidade_pop'])
        mercado_pais = oferta_pais.merge(right=demanda_pais)

        mercado_estado = oferta_estado.merge(right=demanda_estado)

        # df = self.calcular_preco(mercado_estado)
        return (oferta, demanda)



        
    def analisar_construcoes(self):
        h = self.extrair_construcoes()
        hh = pd.Series(h)

        regexs = [
            r'\n(?P<id>\d+)={\n',
            r'levels=(?P<nivel>\d+)',
            r'state=(?P<estado>\d+)',
            r'building=(?P<tipo>[\w_]+)',
            r'goods_cost=(?P<custo_bens>[\d.]+)',
            r'goods_sales=(?P<receita_bens>[\d.]+)',
            r'cash_reserves=(?P<reservas>[\d.]+)',
            r'staffing=(?P<ocupacao>[\d.]+)'


        ]
        xx = self.retornar_trabalhadores()
        # paises = self.retornar_pibs()

        colunas = ['nivel','reservas']

        df = pd.DataFrame(hh.str.extractall(r'|'.join(regexs)).groupby(level=0).first())
        df['id'] = pd.to_numeric(df['id'])
        df = df.merge(right=xx, left_on="id", right_on="workplace")
        df['receita_bens'] = (pd.to_numeric(df['receita_bens']))*52
        df['custo_bens'] = pd.to_numeric(df['custo_bens'])*52
        df['custo_bens']=df['custo_bens'].fillna(0)
        df['valor_agregado'] = (df['receita_bens'] - df['custo_bens'])
        df['produtividade'] = df['valor_agregado']/df['workforce']
        df['lucro'] = df['receita_bens']/52 - df['custo_bens']/52 - df['salario']
        df[colunas] = df[colunas].apply(pd.to_numeric, errors="coerce")
        
        # df = df.merge(right=paises, left_on="estado", right_on="estados")

        # df_copy = df


        # df = df.dropna(subset=['valor_agregado'])

        # ola = pd.DataFrame(df.groupby(['tag'])['valor_agregado'].agg(pib_pais='sum').reset_index())

        # df = df.merge(right=ola, left_on="tag", right_on="tag")
        
        # df = df.merge(right=df.groupby('estado')['pop'].agg(pop_estado='sum').reset_index(), left_on="estado", right_on="estado")

        # df['date']=self.data[0]
        return df

    def retornar_trabalhadores(self):
        h = self.conteudo.split('country_manager')[0].split('job_satisfaction')
        hh = pd.Series(h)

        regexs = [
            r'(?P<id>\d+)={',
            r'workforce=(?P<workforce>\d+)',
            r'dependents=(?P<dependentes>[\d.]+)',
            r'workplace=(?P<workplace>\d+)',
            r'weekly_budget={ (?P<salario>[\d.]+)'

        ]


        df = pd.DataFrame(hh.str.extractall(r'|'.join(regexs)).groupby(level=0).first())
        df['workforce']=pd.to_numeric(df['workforce'])
        df['workplace']=pd.to_numeric(df['workplace'])
        df['dependentes']=pd.to_numeric(df['dependentes'])
        df['salario']=pd.to_numeric(df['salario'])
        df = df.groupby('workplace')[['workforce', 'salario', 'dependentes']].sum()
        df['pop'] = df['workforce'] + df['dependentes']

        return df
    
    def retornar_pibs(self):
        h = self.extrair_paises()
        hh = pd.Series(h)

        regexs = [
            r'definition="(?P<tag>[A-Z]{3})"',
            # r'gdp[\s\S]+?(?P<pib>[\d.]+) }',
            # r'trend_population[\s\S]+?(?P<populacao>[\d.]+) }',
            r'states={ (?P<estados>.+?) }',
            r'population_salaried_workforce=(?P<populacao_assalariada>[\d.]+)'

        ]

        df = pd.DataFrame(hh.str.extractall('|'.join(regexs)).groupby(level=0).first())
        df[['populacao_assalariada']] = df[['populacao_assalariada']].apply(pd.to_numeric, errors='coerce')
        df['estados'] = df['estados'].str.split(' ')

        df = df.explode('estados')

        return df


    def analisar_paises(self):
        h = self.extrair_paises()
        hh = pd.Series(h)

        regexs = [
            r'definition="(?P<tag>[A-Z]{3})"'
            r'weekly_expenses={ (?:\d*\.*\d*\s*){2}(?P<gasto_construcao_gov>[\d.]+)(?:\d*\.*\d*\s*){1}(?P<salario_gov>[\d.]+)(?:\d*\.*\d*\s*){2}(?P<gasto_construcao_mil>[\d.]+)(?:\d*\.*\d*\s*){1}(?P<salario_mil>[\d.]+)(?:\d*\.*\d*\s*){1}(?P<gasto_obras>[\d.]+)(?:\d*\.*\d*\s*){1}(?P<subsidio>[\d.]+)(?:\d*\.*\d*\s*){4}(?P<gasto_ass_social>[\d.]+)',




        ]
        df = pd.DataFrame(hh.str.extractall('|'.join(regexs), flags=re.M|re.DOTALL).groupby(level=0).first())




        
        pass
        
    



if __name__== "__main__":
    pd.set_option('future.no_silent_downcasting', True)
    pd.set_option('display.max_rows', 200)

    bases_nome = {
            'ammunition':50,
            'small_arms':60,
            'artillery':70,
            'tanks':80,
            'aeroplanes':80,
            'manowars':70,
            'ironclads':80,
            'grain':20,
            'fish':20,
            'fabric':20,
            'wood':20,
            'groceries':30,
            'clothes':30,
            'furniture':30,
            'paper':30,
            'services':30,
            'transportation':30,
            'electricity':30,
            'clippers':60,
            'steamers':70,
            'silk':40,
            'dye':40,
            'sulfur':50,
            'coal':30,
            'iron':40,
            'lead':40,
            'hardwood':40,
            'rubber':40,
            'oil':40,
            'engines':60,
            'steel':50,
            'glass':40,
            'fertilizer':30,
            'tools':40,
            'explosives':50,
            'porcelain':70,
            'meat':30,
            'fruit':30,
            'liquor':30,
            'wine':50,
            'tea':50,
            'coffee':50,
            'sugar':30,
            'tobacco':40,
            'opium':50,
            'automobiles':100,
            'telephones':70,
            'radios':80,
            'luxury_clothes':60,
            'luxury_furniture':60,
            'gold':100,
            'fine_art':200,
        }
    bunda = {}
    for i, k in enumerate(bases_nome.keys()):
        bunda[k]=i
    


    x = pd.DataFrame()
    caminho_auto_save = "C:\\Users\\Davi\\Documents\\Paradox Interactive\\Victoria 3\\save games\\autosave.v3"
    caminho = "C:\\Users\\Davi\\Documents\\Paradox Interactive\\Victoria 3\\save games\\"
    caminhos = glob.glob(caminho+"python\\*.v3")

    save = Savegame(caminho_auto_save)

    save.analise_bens(decrescer=False)

    # x = pd.DataFrame()
    # for arquivo in caminhos:
    #     arquivo = "C:\\Users\\Davi\\Documents\\Paradox Interactive\\Victoria 3\\save games\\autosave.v3"
    #     save = Savegame(arquivo)
    #     print(f"\nIniciando leitura do save {arquivo.split('\\')[-1]}...")

    #     df = save.calcular_melhores_construcoes()
    #     print(f"\n\tSave lido.\n\tData: {save.data[0]}\n\tConstru ções: {len(df)}")

    #     x = pd.concat([x, df])
    # x.to_csv('resultado.csv', sep=';', index=False)
    
    # pass