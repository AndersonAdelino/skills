# Design floor

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

## Imagem: a ordem é obrigatória

Foto de site de negócio é afirmação sobre o negócio. Uma recepção bonita gerada
por IA diz "esta é a nossa recepção", e não é. Isso não é estilo, é mentira ao
cliente do cliente.

Procure nesta ordem e **pare na primeira que der certo**:

| | Fonte | Quando usar |
|---|---|---|
| 1 | **Foto real do negócio** | sempre que existir. Perfil do Google, Instagram, Facebook, o site atual, ou o que o dono mandar. Ganha de tudo, mesmo mal enquadrada |
| 2 | **Pexels** | foto real de gente real, licença livre, grátis. Cobre quase tudo |
| 3 | **kie.ai** | só o que sobrou, e **só ilustrativo** |

**O que a IA pode gerar:** cena ilustrativa que não afirma nada sobre aquele
negócio. Uma família feliz, uma textura, um fundo abstrato, um ícone.

**O que a IA não pode gerar, nunca:** a fachada, a recepção, a sala, o
equipamento, a equipe, o produto. Nada que a pessoa vá ler como "é assim que é
lá". Também não: pessoa real identificável, documento, print de notícia, selo,
certificado.

Antes do site subir, toda foto que não é do negócio ganha crédito no rodapé e
uma linha no `PRODUCT.md` avisando o dono que aquilo é ilustrativo e pode ser
trocado por foto real.

Foto do Pexels tem autor. Credite no rodapé, ainda que a licença não exija.

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
