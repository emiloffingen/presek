import os
import logging
import json
import time
import threading
import re
from typing import Optional, Dict, Any, List
from llama_cpp import Llama, LlamaGrammar

log = logging.getLogger("presek.analyst")

# Config for Gemma 2 2B on 2-core CPU
MODEL_PATH = os.environ.get("LOCAL_MODEL_PATH", "models/gemma-2-2b-it-Q4_K_M.gguf")
N_THREADS = int(os.environ.get("MODEL_THREADS", "2")) 
MODEL_CONTEXT = int(os.environ.get("LOCAL_MODEL_CONTEXT", "4096"))
MAX_PROMPT_CHARS = int(os.environ.get("LOCAL_MODEL_MAX_PROMPT_CHARS", "9000"))

# GBNF Grammar for strict JSON
JSON_GBNF = """
root   ::= object
value  ::= object | array | string | number | ("true" | "false" | "null")
object ::= "{" ws ( string ":" ws value ("," ws string ":" ws value)* )? "}" ws
array  ::= "[" ws ( value ("," ws value)* )? "]" ws
string ::= "\\"" ([^"\\\\\\x00-\\x1F] | "\\\\" (["\\\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F]))* "\\"" ws
number ::= ("-"? ([0-9] | [1-9] [0-9]*)) ("." [0-9]+)? ([eE] [-+]? [0-9]+)? ws
ws ::= ([ \\t\\n\\r])*
"""

class LocalAnalyst:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LocalAnalyst, cls).__new__(cls)
                cls._instance.model = None
                cls._instance.load_lock = threading.Lock()
                try:
                    cls._instance.grammar = LlamaGrammar.from_string(JSON_GBNF)
                except Exception as e:
                    log.error(f"[analyst] Failed to compile grammar: {e}")
                    cls._instance.grammar = None
        return cls._instance

    def _load_model(self):
        if self.model is not None:
            return True
        
        with self.load_lock:
            # Check again inside lock to prevent double loading
            if self.model is not None:
                return True

            if not os.path.exists(MODEL_PATH):
                log.warning(f"Local model not found at {MODEL_PATH}. Deep Local tasks will be skipped.")
                return False

            try:
                t0 = time.time()
                # Keep enough context for fallback brief/synthesis while staying within small-host RAM limits.
                self.model = Llama(
                    model_path=MODEL_PATH,
                    n_ctx=MODEL_CONTEXT,
                    n_threads=N_THREADS,
                    verbose=False
                )
                log.info(f"[analyst] Gemma 2 2B loaded in {time.time()-t0:.1f}s")
                return True
            except Exception as e:
                log.error(f"[analyst] Failed to load local model: {e}")
                return False

    def analyze(self, prompt: str, system_prompt: str, max_tokens: int = 512, use_grammar: bool = False) -> Optional[str]:
        if not self._load_model():
            return None

        try:
            prompt = prompt or ""
            system_prompt = system_prompt or ""
            # Enforce literary Macedonian
            if "македонски" not in system_prompt.lower():
                system_prompt = f"Зборувај ИСКЛУЧИВО на стандарден литературен македонски јазик. ЗАБРАНЕТО е користење на бугарски, српски или хрватски зборови или форми. {system_prompt}"

            if len(prompt) > MAX_PROMPT_CHARS:
                prompt = prompt[:MAX_PROMPT_CHARS] + "\n\n[Контекстот е скратен за локалниот модел.]"

            # Gemma 2 Instruct format (optimized for a single user turn).
            full_prompt = f"<start_of_turn>user\n{system_prompt}\n\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
            
            output = self.model(
                full_prompt,
                max_tokens=max_tokens,
                stop=["<end_of_turn>", "<eos>", "###"],
                echo=False,
                temperature=0.1, # Low temperature for analytical consistency
                grammar=self.grammar if use_grammar else None
            )
            return output['choices'][0]['text'].strip()
        except Exception as e:
            log.error(f"[analyst] Generation failed: {e}")
            return None

    def normalize_headline(self, title: str) -> str:
        """Converts sensationalist MK headlines to literary/broadsheet style."""
        system = (
            "Ти си искусен уредник во македонски сериозен весник. "
            "Претвори го насловот во литературен, неутрален и информативен стил. "
            "Отстрани сензационализам, извичници и кликбејт зборови како 'ШОК', 'СКАНДАЛ', 'ЕВЕ ШТО'. "
            "Врати само еден прочистен наслов на македонски јазик.\n\n"
            "ПРИМЕР:\n"
            "Влез: ШОКАНТНО: Мицкоски ја разнесе опозицијата со оваа изјава!!!\n"
            "Излез: Мицкоски упати критики до опозициските партии"
        )
        result = self.analyze(f"Наслов: {title}", system, max_tokens=64)
        return result if result else title

    def extract_deep_metadata(self, text: str) -> Dict[str, Any]:
        """Extracts facts and pulse from Macedonian text."""
        system = (
            "Анализирај го текстот на македонски јазик и врати JSON со следните полиња: "
            "'facts' (листа од 3 клучни факти), 'entities' (листа од имиња и институции), "
            "'sentiment' (позитивен, негативен или неутрален), 'pulse' (од 1 до 100 важност). "
            "Врати само чист JSON.\n\n"
            "ПРИМЕР:\n"
            "Влез: Владата денеска одлучи да ги зголеми пензиите за 5 проценти почнувајќи од септември...\n"
            "Излез: {\"facts\": [\"Зголемување на пензиите за 5%\", \"Мерката стапува на сила од септември\", \"Одлука на Владата\"], \"entities\": [\"Влада\"], \"sentiment\": \"позитивен\", \"pulse\": 75}"
        )
        raw = self.analyze(text[:1500], system, max_tokens=400, use_grammar=True)
        if not raw:
            return {"error": "no_response"}
            
        try:
            return json.loads(raw)
        except Exception as e:
            log.error(f"[analyst] JSON parse failed: {e} | Raw: {raw[:100]}...")
            return {"error": "failed_to_parse"}

    def assess_pluralism(self, titles_with_sources: List[str]) -> Dict[str, Any]:
        """Analyzes if a cluster represents a diverse consensus or an echo chamber."""
        system = (
            "Ти си експерт за медиумски плурализам. Анализирај го диверзитетот на изворите и насловите од Македонија. "
            "Биди многу строг. Ако сите извори се од иста група или имаат ист наслов, дај низок скор (под 40). "
            "Ако има различни перспективи (на пр. про-владини и опозициски извори), дај висок скор (над 70).\n\n"
            "Врати ИСКЛУЧИВО JSON објект со следните клучни зборови:\n"
            "- 'score': цел број од 0 до 100\n"
            "- 'verdict': кратка реченица на македонски која го објаснува скорот\n"
            "- 'bias_detected': точно/неточно (boolean)\n\n"
            "Пример за 'verdict': 'Висок плурализам со разновидни извори и спротивставени ставови.'\n"
        )
        prompt = "АНАЛИЗИРАЈ ГИ ОВИЕ ИЗВОРИ:\n" + "\n".join(titles_with_sources)
        raw = self.analyze(prompt, system, max_tokens=256, use_grammar=True)
        if not raw:
            return {"score": 50, "verdict": "Стандардна покриеност", "bias_detected": False}
            
        try:
            return json.loads(raw)
        except Exception as e:
            log.debug(f"JSON parse error in assess_pluralism: {e}")
            return {"score": 50, "verdict": "Стандардна покриеност", "bias_detected": False}

    def detect_echo(self, article_text: str, cluster_context: str) -> float:
        """Detects if an article is a unique report or just a 'copy-paste' (echo)."""
        system = (
            "Спореди го текстот со контекстот. Дали носи нови информации или е само препишано? "
            "Врати само бројка од 0.0 (целосна копија) до 1.0 (целосно уникатно)."
        )
        prompt = f"ТЕКСТ: {article_text[:500]}\nКОНТЕКСТ: {cluster_context[:1000]}"
        result = self.analyze(prompt, system, max_tokens=10)
        if not result:
            return 1.0
            
        try:
            matches = re.findall(r"[\d.]+", result)
            if matches:
                return float(matches[0])
            return 1.0
        except Exception as e:
            log.debug(f"Echo detection parse error: {e}")
            return 1.0

    def research_query(self, query: str, context: str) -> Dict[str, Any]:
        """Acts as a local researcher providing cited answers and follow-up suggestions."""
        system = (
            "Ти си Пресек Истражувач. Одговори на прашањето користејќи го само дадениот контекст од македонските медиуми. "
            "1. За секој клучен факт или бројка, наведи го името на медиумот во квадратни загради, на пример: [Сител]. "
            "2. На крајот од одговорот, генерирај точно 3 предлог-прашања за следно истражување поврзани со оваа тема. "
            "Врати го одговорот во JSON формат со полиња: 'answer' (текст со цитати) и 'suggestions' (листа од 3 прашања).\n\n"
            "ПРИМЕР:\n"
            "Влез: Кој е најавениот износ за помош?\\nКонтекст: [МТВ] Владата издвои 10 милиони евра...\n"
            "Излез: {\"answer\": \"Владата најави помош во износ од 10 милиони евра [МТВ].\", \"suggestions\": [\"Кога ќе се исплати помошта?\", \"Кој ги исполнува критериумите?\", \"Каков е ефектот врз буџетот?\"]}"
        )
        prompt = f"ПРАШАЊЕ: {query}\nКОНТЕКСТ: {context}"
        raw = self.analyze(prompt, system, max_tokens=800, use_grammar=True)
        
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            # Fallback if JSON fails (though grammar should prevent this)
            return {
                "answer": raw if raw else "Нема доволно информации.",
                "suggestions": ["Кои се клучните актери?", "Каков е економскиот ефект?", "Кои се следните чекори?"]
            }

# Singleton instance
analyst = LocalAnalyst()
