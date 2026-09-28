# Simulador de redes de filas

Trabalho de Simulação e Métodos Analíticos, feito em Python. O programa lê a
rede de um arquivo YAML e simula as chegadas, os atendimentos e as passagens
entre filas. Ao final, mostra o tempo em cada estado e quantos clientes foram
perdidos por falta de espaço.

## Como rodar

É necessário ter Python 3.9 ou superior e instalar o PyYAML:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 simulator.py run modelo_validacao.yml
```

No Windows, use `.venv\Scripts\activate` para ativar o ambiente.

Para salvar o resultado:

```bash
python3 simulator.py run modelo_validacao.yml -o resultado_simulacao.txt
```

Também dá para executar com `./run.sh modelo_validacao.yml` no Linux/macOS.

## Modelo da atividade

O arquivo `modelo_validacao.yml` define três filas. Os tempos estão em minutos
e são sorteados com distribuição uniforme dentro dos intervalos abaixo.

| Fila | Servidores | Capacidade total | Entre chegadas externas | Atendimento |
| --- | --- | --- | --- | --- |
| Q1 | 1 | Ilimitada | 2 a 4 | 1 a 2 |
| Q2 | 2 | 5 | — | 4 a 8 |
| Q3 | 2 | 10 | — | 5 a 15 |

De Q1, 20% dos clientes vão para Q2 e 80% para Q3. De Q2, 30% voltam para Q1,
50% seguem para Q3 e 20% saem da rede. De Q3, 70% vão para Q2 e 30% saem.

As filas começam vazias, com a primeira chegada em Q1 no instante 2.
A execução usa a semente 1 e termina ao consumir 100.000 números aleatórios.

Foi usado o atendimento de 4 a 8 minutos para Q2, conforme o diagrama da
atividade. O texto do arquivo-modelo indica 4 a 6 minutos.

## Como funciona

O código está em `simulator.py`. Os eventos ficam em uma fila de prioridade,
ordenados pelo instante em que acontecem. A cada evento, o simulador acumula
o tempo que cada fila passou com sua quantidade atual de clientes e depois
processa a chegada ou a saída.

Uma chegada encontra um servidor livre e começa o atendimento, espera na fila
ou é contabilizada como perda se a capacidade estiver esgotada. O destino do
cliente é sorteado no início do atendimento. O gerador de aleatórios e a ordem
dos sorteios seguem o simulador da disciplina para permitir a comparação dos
resultados.

## Alterando a rede

Para criar outro modelo, copie `modelo_validacao.yml` ou gere um exemplo menor:

```bash
python3 simulator.py example -o outro_modelo.yml
```

Mantenha a linha `!PARAMETERS`. As seções do YAML são:

- `arrivals`: instante da primeira chegada externa em cada fila de entrada.
- `queues`: servidores (`servers`), capacidade (`capacity`) e limites dos
  tempos de atendimento (`minService` e `maxService`). A capacidade inclui
  quem está em atendimento; quando omitida, é ilimitada. Filas com chegadas
  externas também precisam de `minArrival` e `maxArrival`.
- `network`: rotas com origem (`source`), destino (`target`) e probabilidade
  (`probability`). A probabilidade que sobra corresponde à saída da rede.
- `seeds` e `rndnumbersPerSeed`: sementes e quantidade de sorteios por execução.
  Para usar uma sequência pronta, remova `seeds` e informe a lista em
  `rndnumbers`. Se as duas opções estiverem presentes, `seeds` tem prioridade.

É possível adicionar filas, mais pontos de chegada externa e rotas de retorno.
Com várias sementes, o relatório acumula os tempos e as perdas das execuções.

## Conferência dos resultados

Para o modelo incluído, o tempo total é **50736.0338 minutos**. As perdas são:

| Q1 | Q2 | Q3 |
| --- | --- | --- |
| 0 | 39 | 11664 |

Q3 fica cheia durante 63,36% do tempo e concentra a maior parte das perdas.
Os tempos por estado estão em `resultado_simulacao.txt`. A saída de referência
está em `resultado_referencia_professor.txt`; os valores coincidem nas casas
decimais exibidas.

Para rodar os quatro testes de tempo total, perdas, consumo de aleatórios e
alguns tempos por estado:

```bash
python3 -m unittest -v
```

Se tiver o `simulator.jar` da disciplina, a comparação pode ser repetida com:

```bash
java -jar simulator.jar run modelo_validacao.yml
python3 simulator.py run modelo_validacao.yml
```
# simulador-rede-de-filas
