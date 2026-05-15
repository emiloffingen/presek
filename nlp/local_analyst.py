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
                log.warning(
                    f"Local model not found at {MODEL_PATH}. Deep Local tasks will be skipped."
                )
                return False

            try:
                t0 = time.time()
                # Keep enough context for fallback brief/synthesis while staying within small-host RAM limits.
                self.model = Llama(
                    model_path=MODEL_PATH,
                    n_ctx=MODEL_CONTEXT,
                    n_threads=N_THREADS,
                    verbose=False,
                )
                log.info(f"[analyst] Gemma 2 2B loaded in {time.time()-t0:.1f}s")
                return True
            except Exception as e:
                log.error(f"[analyst] Failed to load local model: {e}")
                return False

    def analyze(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 512,
        use_grammar: bool = False,
    ) -> Optional[str]:
        if not self._load_model():
            return None

        try:
            prompt = prompt or ""
            system_prompt = system_prompt or ""
            # Enforce literary Macedonian
            if "makedonski" not in system_prompt.lower():
                system_prompt = f"Zboruvaj ISKLUCIVO na standarden literaturen makedonski jazik. ZABRANETO e koristenje na bugarski, srpski ili hrvatski zborovi ili formi. {system_prompt}"

            if len(prompt) > MAX_PROMPT_CHARS:
                prompt = (
                    prompt[:MAX_PROMPT_CHARS]
                    + "\n\n[Kontekstot e skraten za lokalniot model.]"
                )

            # Gemma 2 Instruct format (optimized for a single user turn).
            full_prompt = f"<start_of_turn>user\n{system_prompt}\n\n{prompt}<end_of_turn>\n<start_of_turn>model\n"

            output = self.model(
                full_prompt,
                max_tokens=max_tokens,
                stop=["<end_of_turn>", "<eos>", "###"],
                echo=False,
                temperature=0.1,  # Low temperature for analytical consistency
                grammar=self.grammar if use_grammar else None,
            )
            return output["choices"][0]["text"].strip()
        except Exception as e:
            log.error(f"[analyst] Generation failed: {e}")
            return None

    def normalize_headline(self, title: str) -> str:
        """Converts sensationalist RS headlines to literary/broadsheet style."""
        system = (
            "Ti si iskusen urednik vo makedonski seriozen vesnik. "
            "Pretvori ga naslovot vo literaturen, neutralen i informativen stil. "
            "Otstrani senzacionalizam, izvicnici i klikbejt zborovi kako 'SOK', 'SKANDAL', 'EVE STO'. "
            "Vrati samo eden procisten naslov na makedonski jazik.\n\n"
            "PRIMER:\n"
            "Vlez: SOKANTNO: Mickoski me raznese opozicijata so ova izjava!!!\n"
            "Izlez: Mickoski upati kritiki do opoziciskite partii"
        )
        result = self.analyze(f"Naslov: {title}", system, max_tokens=64)
        return result if result else title

    def extract_deep_metadata(self, text: str) -> Dict[str, Any]:
        """Extracts facts and pulse from Macedonian text."""
        system = (
            "Analiziraj ga tekstot na makedonski jazik i vrati JSON so slednite polinja: "
            "'facts' (lista od 3 klucni fakti), 'entities' (lista od iminja i institucii), "
            "'sentiment' (pozitiven, negativen ili neutralen), 'pulse' (od 1 do 100 vaznost). "
            "Vrati samo cist JSON.\n\n"
            "PRIMER:\n"
            "Vlez: Vladata danas odluci da im zgolemi penziite za 5 procenti pocnuvajci od septembar...\n"
            'Izlez: {"facts": ["Zgolemuvanje na penziite za 5%", "Merkata stapuva na sila od septembar", "Odluka na Vladata"], "entities": ["Vlada"], "sentiment": "pozitiven", "pulse": 75}'
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
            "Ti si ekspert za mediumski pluralizam. Analiziraj ga diverzitetot na izvorite i naslovite od Srbija. "
            "Bidi mnogu strog. Ako site izvori se od ista grupa ili imaat ist naslov, daj nizok skor (pod 40). "
            "Ako ima razliciti perspektivi (na pr. pro-vladini i opoziciski izvori), daj visok skor (nad 70).\n\n"
            "Vrati ISKLUCIVO JSON objekt so slednite klucni zborovi:\n"
            "- 'score': cel broj od 0 do 100\n"
            "- 'verdict': kratka recenica na makedonski koja ga objasnuva skorot\n"
            "- 'bias_detected': tocno/netocno (boolean)\n\n"
            "Primer za 'verdict': 'Visok pluralizam so raznovidni izvori i sprotivstaveni stavovi.'\n"
        )
        prompt = "ANALIZIRAJ im OVIE izvori:\n" + "\n".join(titles_with_sources)
        raw = self.analyze(prompt, system, max_tokens=256, use_grammar=True)
        if not raw:
            return {
                "score": 50,
                "verdict": "Standardna pokrienost",
                "bias_detected": False,
            }

        try:
            return json.loads(raw)
        except Exception as e:
            log.debug(f"JSON parse error in assess_pluralism: {e}")
            return {
                "score": 50,
                "verdict": "Standardna pokrienost",
                "bias_detected": False,
            }

    def detect_echo(self, article_text: str, cluster_context: str) -> float:
        """Detects if an article is a unique report or just a 'copy-paste' (echo)."""
        system = (
            "Sporedi ga tekstot so kontekstot. Dali nosi novi informacii ili e samo prepisano? "
            "Vrati samo brojka od 0.0 (celosna kopija) do 1.0 (celosno unikatno)."
        )
        prompt = f"TEKST: {article_text[:500]}\nKONTEKST: {cluster_context[:1000]}"
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
            "Ti si Presek Istrazuvac. odgovori na prasanjeto koristejci ga samo dadeniot kontekst od makedonskite mediumi. "
            "1. Za sekoj klucen fakt ili brojka, navedi ga imeto na mediumot vo kvadratni zagradi, na primer: [Sitel]. "
            "2. Na krajot od odgovorot, generiraj tocno 3 predlog-prasanja za sledece istrazuvanje povrzani so ova tema. "
            "Vrati ga odgovorot vo JSON format so polinja: 'answer' (tekst so citati) i 'suggestions' (lista od 3 prasanja).\n\n"
            "PRIMER:\n"
            "Vlez: Koj e najaveniot iznos za pomos?\\nKontekst: [MTV] Vladata izdvoi 10 milioni evra...\n"
            'Izlez: {"answer": "Vladata najavi pomos vo iznos od 10 milioni evra [MTV].", "suggestions": ["Koga ce se isplati pomosta?", "Koj im ispolnuva kriteriumite?", "Kakov e efektot vrz budzetot?"]}'
        )
        prompt = f"PRASANjE: {query}\nKONTEKST: {context}"
        raw = self.analyze(prompt, system, max_tokens=800, use_grammar=True)

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            # Fallback if JSON fails (though grammar should prevent this)
            return {
                "answer": raw if raw else "Nema dovolno informacii.",
                "suggestions": [
                    "Koi se klucnite akteri?",
                    "Kakov e ekonomskiot efekt?",
                    "Koi se slednite cekori?",
                ],
            }


# Singleton instance
analyst = LocalAnalyst()
