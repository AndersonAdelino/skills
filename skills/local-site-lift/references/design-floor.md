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

## Cópia

Palavra é design. Frase curta. Voz ativa. CTA diz o que acontece: "Chamar no WhatsApp", "Ver no mapa".

Não venda o sistema. Fale o que o cliente ganha na cidade dele. Horário, bairro e "fica em frente a X" valem mais que slogan.

Estado vazio e erro (mapa que não carrega, foto ausente) explicam o próximo passo. Não façam graça.
