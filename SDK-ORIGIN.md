# Origem e atualização do Mage Core

A cópia de reserva em `r36s_a11y/` corresponde à main de
[gogabs/r36s-a11y-sdk](https://github.com/gogabs/r36s-a11y-sdk) no commit
registrado em `sdk-origin.json`, com os hashes dos arquivos. Não há patches
exclusivos do Vinyl. O Vinyl usa `game.keep_awake` quando o Mage Core tiver;
senão, grava o mesmo arquivo sozinho (`vinyl/awake.py`).

O instalador prefere um clone do Mage Core ao lado deste repositório e usa a
cópia incluída como reserva. Para atualizar a cópia de reserva:

```sh
python3 tools/sync_sdk.py --sdk ../r36s-a11y-sdk
cd tests && python3 -m unittest discover -s .
git diff -- r36s_a11y sdk-origin.json
```
