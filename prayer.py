# 기도시간 관련 로직이에요. (aladhan API 활용)
import httpx
from datetime import datetime


async def fetch_prayer_times(lat: float, lng: float):
    today = datetime.now()
    date_str = f"{today.day}-{today.month}-{today.year}"

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"https://api.aladhan.com/v1/timings/{date_str}",
                params={"latitude": lat, "longitude": lng, "method": 3}
            )
            data = res.json()

        if data.get("code") == 200:
            timings = data["data"]["timings"]
            return {
                "Fajr": timings["Fajr"],
                "Dhuhr": timings["Dhuhr"],
                "Asr": timings["Asr"],
                "Maghrib": timings["Maghrib"],
                "Isha": timings["Isha"],
            }
        return {"error": "기도 시간을 불러오지 못했어요"}

    except Exception as e:
        print(f"기도시간 API 오류: {e}")
        return {"error": "기도 시간을 불러오지 못했어요"}
