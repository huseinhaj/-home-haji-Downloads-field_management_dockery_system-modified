# 🖨️ Sahishi Bridge

Programu ndogo inayokaa **PC ya shule (Ubuntu)** inayounganisha **scanner ya ADF**
moja kwa moja na site ya Sahishi. Mwalimu anabonyeza "Anza Scan" kwenye site —
bridge inascan kurasa na kuzituma moja kwa moja.

## Usanidi (mara moja)

```bash
# 1. Sakinisha SANE (scanner drivers za Linux)
sudo apt install sane sane-utils python3-pip python3-venv

# 2. Tengeneza folder na u-copy bridge.py kutoka repo
mkdir -p ~/sahishi_bridge && cd ~/sahishi_bridge
# copy bridge.py hapa

# 3. Sakinisha requests
python3 -m venv venv
./venv/bin/pip install requests

# 4. Tengeneza config
cat > .env <<'EOF'
SAHISHI_SERVER=https://your-site.up.railway.app
SAHISHI_TOKEN=sb_xxxxxxxxxxxxxxxxxxxxxx
EOF

# 5. Thibitisha scanner inaonekana
scanimage -L
```

## Kupata token

1. Admin wa shule (Academic) anaenda Django admin → **Sahishi Bridges** → Add
2. Chagua shule, weka jina (mf. "Ofisi"), hifadhi — **token inaundwa moja kwa moja**
3. Copy token kwenye `.env` ya bridge

## Kuanza

```bash
# Thibitisha kila kitu sawa
python3 bridge.py --status

# Anza kusikiliza kazi (mara ya kudumu)
python3 bridge.py --serve
```

## Kwenye site (mwalimu)

1. Fungua mtihani → somo → **Sahishi Scan** → **🖨️ Scan kwa Bridge (ADF live)**
2. Weka karatasi kwenye ADF → bonyeza **Anza Scan**
3. Ukurasa unaonyesha: *Inasubiri bridge → Bridge inascan → Inatuma → Imekamilika*
4. Mwalimu anaenda review — karatasi zimesahihishwa

## Kuweka kama service (inaanza yenyewe PC inapowashwa)

```bash
sudo tee /etc/systemd/system/sahishi-bridge.service <<'EOF'
[Unit]
Description=Sahishi Bridge - ADF scanner
After=network-online.target

[Service]
User=PUT_USERNAME_HERE
WorkingDirectory=/home/PUT_USERNAME_HERE/sahishi_bridge
ExecStart=/home/PUT_USERNAME_HERE/sahishi_bridge/venv/bin/python bridge.py --serve
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now sahishi-bridge
sudo systemctl status sahishi-bridge
```

## Tatua matatizo

| Tatizo | Suluhisho |
|---|---|
| `scanimage -L` haionii scanner | `sudo apt install sane-airscan` kwa scanner za mtandao; `sudo usermod -aG scanner $USER` kwa USB |
| Bridge haionekani "online" | Angalia `SAHISHI_SERVER` (bila `/` mwisho) na token |
| Scan zinaanguka katikati | Punguza kurasa (mf. 20 badala ya 40) au `dpi=200` |
| Permission denied kwenye USB | Ongeza user kwenye group `scanner` na `lp`, kisha restart |
