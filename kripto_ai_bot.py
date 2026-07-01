
import os
import asyncio
import ccxt.pro as ccxtpro  # Aszinkron CCXT verzió
import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import Literal

# 1. Google Gemini API konfigurálása
# Megjegyzés: Mindig ellenőrizd az aktuálisan legfrissebb modellt (pl. gemini-1.5-flash vagy gemini-2.0 verziók)
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# 2. A Strukturált Kimenet definíciója Pydantic-kal
class TradingDecision(BaseModel):
    decision: Literal["BUY", "SELL", "HOLD"] = Field(description="A végrehajtandó kereskedési művelet.")
    confidence: float = Field(description="A döntés magabiztossága 0.0 és 1.0 között.")
    stop_loss_pct: float = Field(description="Javasolt stop-loss százalék a jelenlegi árhoz képest (pl. 0.02 = 2%).")
    reasoning: str = Field(description="Rövid indoklás, hogy a kapott adatok alapján miért ezt a döntést hoztad.")

# 3. Binance Testnet (Homokozó) kliens inicializálása
exchange = ccxtpro.binance({
    'apiKey': 'A_TE_BINANCE_TESTNET_API_KULCSOD',
    'secret': 'A_TE_BINANCE_TESTNET_SECRET_KULCSOD',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',  # Spot piacot használunk
    }
})
exchange.set_sandbox_mode(True)  # KRITIKUS: Ez kapcsolja be a játékpénzes Testnet módot!

async def get_market_data(symbol: str):
    """Lekéri a legfrissebb piaci adatokat a Binance-ről."""
    try:
        # Lekérjük az utolsó 5 db 15 perces gyertyát (OHLCV adatok)
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe='15m', limit=5)
        # Lekérjük az aktuális árat (ticker)
        ticker = await exchange.fetch_ticker(symbol)
        
        # Egyszerűsített adatcsomag az MI számára
        market_summary = {
            "current_price": ticker['last'],
            "high_24h": ticker['high'],
            "low_24h": ticker['low'],
            "recent_candles_close": [candle[4] for candle in ohlcv]  # Csak a záróárak
        }
        return market_summary
    except Exception as e:
        print(f"❌ Hiba a piaci adatok lekérésekor: {e}")
        return None

async def ask_gemini_decision(market_data: dict, symbol: str) -> TradingDecision:
    """Átadja az adatokat a Gemini-nek és kikényszeríti a strukturált döntést."""
    # A legújabb, leggyorsabb modell kiválasztása
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Te egy teljesen autonóm, profi kriptovaluta kereskedő bot vagy.
    Elemezd a következő piaci adatokat a(z) {symbol} párhoz, és hozz döntést.
    
    Aktuális piaci adatok:
    {market_data}
    
    A kockázatkezelési szabályzatod szerint szigorúan a megadott JSON sémában kell válaszolnod!
    """
    
    # Itt kötelezzük a Gemini-t, hogy a Pydantic sémánk szerint válaszoljon
    response = await model.generate_content_async(
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=TradingDecision
        )
    )
    
    # A Gemini SDK automatikusan validálja és beparszolja a sémát, ha a response.text-et áttoljuk rajta
    return TradingDecision.model_validate_json(response.text)

async def execute_trade(symbol: str, decision_data: TradingDecision):
    """Végrehajtja a tőzsdei megbízást a döntés alapján."""
    if decision_data.decision == "HOLD":
        print(f"😴 MI Döntés: HOLD. Indoklás: {decision_data.reasoning}")
        return

    print(f"🚀 MI Döntés: {decision_data.decision} (Biztonság: {decision_data.confidence * 100:.1f}%)")
    print(f"💡 Indoklás: {decision_data.reasoning}")

    try:
        if decision_data.decision == "BUY":
            # Példa: veszünk egy minimális összeget (pl. 0.001 BTC piaci áron)
            # Figyelem: élesben az egyenleged és a minimális order size korlátokat ellenőrizni kell!
            order = await exchange.create_market_buy_order(symbol, 0.001)
            print(f"✅ Sikeres VÉTEL! Order ID: {order['id']}")
            
        elif decision_data.decision == "SELL":
            order = await exchange.create_market_sell_order(symbol, 0.001)
            print(f"✅ Sikeres ELADÁS! Order ID: {order['id']}")
            
    except Exception as e:
        print(f"❌ Kereskedési hiba a Binance-en: {e}")

async def main_loop():
    """A bot fő eseményvezérelt hurka."""
    symbol = "BTC/USDT"
    print("🤖 Automata MI Kereskedő Bot elindítva (Binance Testnet + Gemini API)...")
    
    try:
        while True:
            print("\n🔄 Új elemzési ciklus indul...")
            
            # 1. Lépés: Adatgyűjtés
            market_data = await get_market_data(symbol)
            
            if market_data:
                # 2. Lépés: Döntéshozatal az MI segítségével
                print("🧠 Gemini elemzés folyamatban...")
                decision = await ask_gemini_decision(market_data, symbol)
                
                # 3. Lépés: Végrehajtás
                await execute_trade(symbol, decision)
            
            # 4. Lépés: Várakozás a következő ciklusig (pl. 5 perc = 300 másodperc)
            print("⏳ Várakozás a következő ciklusig...")
            await asyncio.sleep(300)
            
    finally:
        # Lezárjuk a kapcsolatokat, ha leállítjuk a botot (Ctrl+C)
        await exchange.close()

if __name__ == "__main__":
    # Aszinkron hurok indítása
    asyncio.run(main_loop())
