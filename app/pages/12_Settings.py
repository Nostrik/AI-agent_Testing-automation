import streamlit as st

from core import storage
from core.llm import LLM

st.title("⚙️ Настройки")
s = storage.get_settings()

st.subheader("LLM для судьи, клиента и аналитика")
st.caption("Любой OpenAI-совместимый провайдер: OpenRouter, локальная Ollama (http://localhost:11434/v1) и т.д.")
s["llm_base_url"] = st.text_input("Base URL", s["llm_base_url"])
s["llm_api_key"] = st.text_input("API-ключ", s["llm_api_key"], type="password")
c1, c2, c3 = st.columns(3)
s["judge_model"] = c1.text_input("Модель судьи", s["judge_model"])
s["client_model"] = c2.text_input("Модель клиента/помощника", s["client_model"])
s["analyst_model"] = c3.text_input("Модель аналитика", s["analyst_model"])
s["fallback_models"] = st.text_input("Запасные модели через запятую", s["fallback_models"])

st.subheader("Тест и метрики")
c1, c2, c3 = st.columns(3)
s["max_turns"] = c1.number_input("Макс. реплик клиента в диалоге", 2, 40, int(s["max_turns"]))
s["slow_threshold_s"] = c2.number_input("Порог «долгой паузы», с", 0.5, 10.0, float(s["slow_threshold_s"]), 0.5)
s["network_offset_s"] = c3.number_input("Вычет сети на реплику, с", 0.0, 2.0, float(s["network_offset_s"]), 0.01)

c1, c2 = st.columns(2)
if c1.button("💾 Сохранить", type="primary"):
    storage.save_settings(s)
    st.success("Сохранено")
if c2.button("🧪 Проверить модель судьи"):
    try:
        st.success(LLM.from_settings(s).chat(s["judge_model"], [{"role": "user", "content": "Ответь одним словом: столица России?"}],
                                             max_tokens=50))
    except Exception as e:  # noqa: BLE001
        st.error(str(e))
