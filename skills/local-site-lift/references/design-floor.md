# Design floor

## Antes de tudo: contenção não é vazio

Este documento já foi só uma lista de proibições, e o resultado saiu duas vezes:
site plano, sem contraste, com metade da tela vazia. Um agente lendo só
"evite isto" joga seguro, e seguro parece barato.

**O chão abaixo é numérico e medido.** Rode antes de mostrar qualquer coisa:

```bash
python scripts/aferir.py dist/
```

| | Mínimo | Por quê |
|---|---|---|
| `h1` no desktop | **3,5rem** (56px) | 2,5rem num monitor lê como subtítulo |
| `h1` ÷ corpo | **2,6×**, mire 3× | abaixo disso não há hierarquia, só tamanhos parecidos |
| Tamanhos de fonte | **no máximo 8**, cada um 12% maior que o anterior | 10 tamanhos com 7 entre 0,85 e 1,15rem é ruído, não escala |
| Estados `:hover` | **4** | com 2 em 75 regras, nada responde ao cursor |
| `transition` | **3** | troca seca de estado é o que mais denuncia amador |
| Grade de várias colunas no desktop | **1** | sem isso o layout largo é a coluna do celular esticada |
| `<footer>` | existe | site sem rodapé termina no ar |

**Nunca ponha `max-width` em `ch` num título.** `h1 { max-width: 18ch }` foi o
defeito central de um site real: o título quebrava em três linhas curtas e
metade da tela ficava vazia ao lado. Título respira em largura, não em coluna
de leitura. `ch` é para parágrafo.

Passar no chão não faz um site bonito. **Falhar garante um que parece barato.**

## O desktop não é o celular esticado

"Mobile primeiro" é ordem de construção, não desculpa para nunca desenhar o
desktop. Numa tela de 1440px:

- o conteúdo usa a largura. Uma coluna de 420px alinhada à esquerda, com o
  resto vazio, é o erro mais visível que existe
- pelo menos uma seção tem duas colunas de verdade: texto de um lado, imagem
  ou lista do outro
- o herói ocupa a primeira tela com intenção: título grande, uma linha de
  apoio, um botão, e uma imagem que não é enfeite
- seções alternam fundo, para o olho saber onde uma acaba



Direção visual destilada para site de comércio local. Use como chão de qualidade, não como lista de efeitos.

Inspirado em técnicas de direção de frontend (escolha deliberada, assunto primeiro, um gesto ousado) e em craft de produção (um ciclo de inspeção, anti-padrão, acessível no celular). Reescrito para este método. Não copie skills de terceiros.

## O assunto manda

A cara do site sai do negócio real: farinha e forma, óleo e metal, jaleco, cadeira de salão, cheiro de pão. Paleta, tipo e foto vêm daí. Se o plano visual serviria igual para um SaaS, descarte.

Gaste ousadia em um lugar só — hero, tipo de título ou uma foto grande. O resto fica quieto.

## Plano antes do código

Em `DESIGN.md` fixe:

- 4 a 6 cores nomeadas (hex), com papel (fundo, texto, ação, apoio)
- uma família para título e uma para texto, ou uma só
- layout em uma frase + wire ASCII da home no mobile
- o elemento que a pessoa vai lembrar

Revise o plano contra a lista de defaults abaixo. Se qualquer eixo livre caiu num default, troque e anote o porquê. Só então escreva HTML.

## Defaults que denunciam site gerado

Evite estes looks quando o brief não pediu explicitamente:

- creme quente + serif + terracota
- fundo preto + um neon
- layout de jornal com filete em tudo
- kit SaaS — cards idênticos, mesma sombra, mesmo raio, wash de degradê
- eyebrow em caixa alta acima de todo título
- meta com ponto médio (`A · B · C`)
- rótulo `PALAVRA — fragmento`
- uma palavra do título em outra cor ou itálico
- seta `→` no fim de todo botão
- Inter / Arial / Roboto como personalidade
- glassmorphism, texto em degradê, grid decorativo de linhas

Estrutura visual informa. Numeração `01 / 02 / 03` só se o conteúdo for sequência de verdade.

## Tipo, cor, espaço, motion

Tipo carrega personalidade. Duas famílias no máximo, escala curta, linha de texto abaixo de ~80 caracteres. Título pode ser o gesto. Texto corre sem frescura.

Cor tem dono. Uma cor de ação (o botão do WhatsApp). Fundo e texto com contraste real. Variáveis CSS na `:root`.

Espaço é ritmo, não margem aleatória. Seções respiram. No mobile, o dedo precisa do botão grande e do número visível sem pinça.

Motion só responde a um gesto da pessoa (abrir menu, confirmar) ou a um único momento na entrada. Fade+slide em toda seção é default de IA.

## Chão de produção

O site sobe em hospedagem compartilhada e é aberto no 4G, no sol, com uma mão.

- legível no celular de 360px sem scroll horizontal
- contraste de texto suficiente
- foco de teclado visível
- `prefers-reduced-motion` respeitado
- imagens com tamanho realista (não 4k no hero)
- um `h1`, heading em ordem
- tap targets de CTA com área folgada

## Imagem

Foto de site de negócio é **afirmação sobre o negócio**. Uma recepção bonita
gerada por IA diz "esta é a nossa recepção", e não é. Isso não é estilo, é
mentira ao cliente do cliente.

**Quem decide é você, não o script.** `scripts/imagens.py` só executa: `buscar`
lista, `pegar` baixa o id que você escolheu, `gerar` usa o prompt que você
escreveu. Ele nunca troca de fonte sozinho.

### Primeiro: essa imagem afirma algo sobre este negócio?

Fachada, recepção, sala, equipamento, equipe, o produto que eles fazem, o prato
que eles servem. Se sim, ela **só pode ser foto real deles**. Vale mesmo mal
enquadrada. Não existindo foto real, **a seção não leva imagem** — um bloco de
texto honesto é melhor que uma foto que mente.

Onde procurar, em ordem de quem entrega:

| | |
|---|---|
| **Perfil do Google** | `scripts/negocio.py`. A única que funcionou no primeiro site real |
| O dono | pede. É a melhor, e a que ninguém lembra de pedir |
| Site atual | confira: costuma ser banco de imagem. No primeiro teste, era |
| Instagram, Facebook | bloqueiam requisição sem login |

Foto do perfil do Google é mistura de foto do dono e de cliente, e pode ter
rosto de funcionário. **Rosto identificável não se publica sem consentimento.**
Toda foto daí é candidata marcada no `PRODUCT.md`, nunca publicação direta.

Nunca gere: pessoa real identificável, documento, print de notícia, selo,
certificado, avaliação.

### Depois: o que a imagem precisa ser?

| Se... | Use | Porque |
|---|---|---|
| é um **assunto comum do mundo real**, que alguém já fotografou | **Pexels** | pão saindo do forno, mãos de idoso, rua de interior, criança no colo, cadeira de dentista. Se você consegue imaginar essa foto existindo num banco, ela existe |
| é **específico da ideia deste site**, e não existiria como stock | **kie.ai** | uma composição na paleta da marca, uma cena que amarra com a manchete, uma textura, um padrão de fundo, um ícone que combina com o resto |

O teste prático: **busque no Pexels primeiro**, porque é grátis e a busca já
responde a pergunta. Olhe as prévias. Se o que voltar serve, acabou. Se voltar
genérico demais, fora de tom, ou nada com o que a copy diz, **é sinal de que a
imagem é específica demais para stock** — aí gere.

```bash
python scripts/imagens.py buscar "pao saindo do forno padaria" --n 5 --previa /tmp/p
# olhe as previas, escolha
python scripts/imagens.py pegar 7447284 --out dist/img/hero
# se nada servir:
python scripts/imagens.py gerar "<prompt em ingles>" --out dist/img/hero
```

Busque em **inglês**: o acervo do Pexels é muito maior. Escolher às cegas dá
errado — numa busca por "família feliz" para uma clínica no Seridó, o primeiro
resultado foi uma marina com bandeira dos EUA.

### Depois de escolher

- **Crédito no rodapé.** O comando imprime o autor. A licença do Pexels não
  exige, mas credite
- **Uma linha no `PRODUCT.md`** avisando o dono de que aquilo é ilustrativo e
  pode ser trocado por foto real das instalações dele
- O `imagens.py` já redimensiona e converte para webp. Acima de 150 KB ele
  reclama: atenda

## Depoimento

Só com nome e data reais. A fonte natural é o perfil do Google do negócio, que
é público.

**Leia as avaliações ruins também, e conte ao dono.** Elas quase sempre apontam
um problema operacional que o site não conserta e não deve esconder. Se a
queixa recorrente for "demora" ou "desorganização", isso é informação de
negócio mais valiosa que o site inteiro, e a copy não pode prometer o contrário
do que os clientes relatam.

Nunca publique nota agregada que você não conseguiu verificar. Sem
`aggregateRating` no schema por dedução.

## Cópia

Palavra é design. Frase curta. Voz ativa. CTA diz o que acontece: "Chamar no WhatsApp", "Ver no mapa".

**Travessão é proibido.** Nunca `—` nem `–` em texto que o cliente lê. É a
pontuação que mais denuncia texto gerado, e ninguém escreve assim. Onde daria
vontade de usar, quebre a frase:

| Não | Sim |
|---|---|
| `Rua Manoel Felipe, 23 — CEP 59300-000` | `Rua Manoel Felipe, 23. CEP 59300-000` |
| `Clínica Fácil — consultas e exames` | `Clínica Fácil: consultas e exames` |

Ponto, vírgula ou dois-pontos. O ponto médio (`A · B · C`) também não serve:
já está na lista de defaults que denunciam site gerado.

Não venda o sistema. Fale o que o cliente ganha na cidade dele. Horário, bairro e "fica em frente a X" valem mais que slogan.

Estado vazio e erro (mapa que não carrega, foto ausente) explicam o próximo passo. Não façam graça.
