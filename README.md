# Vinyl

Player de audiolivros e música do Luma, com menus falados. Lê duas pastas do
cartão (partição EASYROMS): `audiolivros` e `musica`. Quem toca é o
[mpv](https://mpv.io) sem interface; o Vinyl fala os menus, guarda onde cada
livro parou e manda os comandos ao mpv por um socket.

## Pondo livros e músicas no cartão

- **Audiolivros**: uma pasta por livro dentro de `audiolivros`, com um
  arquivo por capítulo (subpastas como `CD 1` e `CD 2` entram na ordem), ou
  um arquivo só, como um `.m4b` com capítulos embutidos. A ordem é a dos
  nomes, com números em ordem de gente (`Capítulo 2` antes de `Capítulo 10`).
- **Música**: qualquer árvore de pastas dentro de `musica`.
- Formatos: MP3, M4A/M4B, AAC, OGG, Opus, FLAC, WAV e WMA.

## Controles

Na biblioteca, o menu falado de sempre: cima e baixo escolhem, B confirma,
A volta (no menu principal, A sai do Vinyl). O menu principal tem
"Continuar" com o último livro ou pasta, "Audiolivros" e "Música". Cada livro
fala quanto já foi ouvido, ou o capítulo em que parou.

Na tela de reprodução:

| Botão | Audiolivro | Música |
| --- | --- | --- |
| B | Tocar e pausar | Tocar e pausar |
| Esquerda e direita | Voltar e avançar 30 s | Faixa anterior e seguinte |
| L2 e R2 | Voltar e avançar 5 min | Voltar e avançar 30 s |
| L1 e R1 | Capítulo anterior e seguinte | Pasta anterior e seguinte |
| Cima e baixo | Velocidade, de 0,05 em 0,05 (0,5 a 3 vezes, sem mudar o tom) | Cima liga o aleatório, baixo liga o repetir |
| X | Criar marcador | — |
| Y | Marcadores (B vai, X apaga) | — |
| Select | Falar capítulo, minuto, quanto falta e a velocidade | Falar faixa e artista |
| Start | Opções: timer, ir para capítulo, marcadores, velocidade normal | Opções: timer, aleatório, repetir |
| A | Volta à biblioteca sem parar o som | Igual |

Voltar capítulo (ou faixa) depois de 3 segundos volta ao começo dele; mais
um aperto vai ao anterior. Segurar esquerda, direita, cima, baixo, L2 ou R2
repete. O volume é o do rocker, pelo a11yd. Enquanto a voz fala, o som abaixa
para 40%.

O **timer para dormir** (Start, Timer) pausa em 15, 30, 45 ou 60 minutos, ou
no fim do capítulo. Nos últimos 30 segundos o volume vai baixando.

## Onde fica cada coisa

- Posição, velocidade e marcadores de cada livro, e a última pasta de
  música: `/roms/a11y/saves/vinyl/vinyl.json`, gravado a cada 15 s tocando,
  ao pausar e ao sair.
- Enquanto toca, o Vinyl cria `$XDG_RUNTIME_DIR/a11y-reproduzindo` com o seu
  PID. O a11yd não suspende sozinho enquanto ele existe e apaga a tela 10 s
  depois do último botão. Pausado, a suspensão automática volta a valer.
- Apertar Power suspende como sempre; na volta o livro fica pausado.
- Sair do Vinyl (ou Fn + Start por 3 s) pausa e grava.

## Instalar

O mpv vem do instalador da plataforma
([r36s-a11y](https://github.com/gogabs/r36s-a11y), `instalar/console/setup.sh`),
que também cria as pastas `audiolivros` e `musica`. Sem o mpv, o Vinyl abre,
avisa e sai. Depois, do PC, com o SSH via USB ligado:

```sh
./instalar.sh r36s
```

Também dá para copiar a pasta do Vinyl, com a `r36s_a11y` dentro, para
`a11y/games/vinyl` no cartão.

## Testes

```sh
cd tests && python3 -m unittest discover -s .
```

Os testes usam a cópia de reserva do Mage Core em `r36s_a11y/`
(`A11Y_SDK=<pasta>/python` escolhe outra). Os de
`test_mpv_real.py` rodam o mpv de verdade com saída nula e são pulados se ele
não estiver instalado.
