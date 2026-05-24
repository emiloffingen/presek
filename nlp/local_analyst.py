import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from llama_cpp import Llama, LlamaGrammar
from pydantic import BaseModel, Field

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


class DeepMetadataResponse(BaseModel):
    facts: List[str] = Field(..., description="Exactly 3 key facts extracted from the text")
    entities: List[str] = Field(..., description="List of key entities (names, institutions, etc.) mentioned in the text")
    sentiment: str = Field(..., description="Sentiment: positive/negativan/neutralan, etc.")
    pulse: int = Field(..., ge=1, le=100, description="Significance pulse rating from 1 to 100")


class PluralismResponse(BaseModel):
    score: int = Field(..., ge=0, le=100, description="Pluralism score from 0 to 100")
    verdict: str = Field(..., description="A short sentence explaining the score")
    bias_detected: bool = Field(..., description="Whether bias was detected")


class ResearchQueryResponse(BaseModel):
    answer: str = Field(..., description="Answer with media source citations like [RTS]")
    suggestions: List[str] = Field(..., description="Exactly 3 suggested follow-up research questions")


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
        lang: str = "mk",
        response_schema: Optional[Any] = None,
    ) -> Optional[str]:
        # Try remote API first if enabled (default True)
        if os.environ.get("USE_REMOTE_ANALYST", "true").lower() == "true":
            try:
                from core.ai_engine import sync_call_ai

                raw, provider = sync_call_ai(
                    prompt=prompt,
                    system=system_prompt,
                    task_type="analyst",
                    max_tokens=max_tokens,
                    json_mode=(use_grammar or response_schema is not None),
                    lang=lang,
                    response_schema=response_schema,
                )
                if raw:
                    log.info(f"[analyst] Remote generation successful using {provider}")
                    return raw
            except Exception as e:
                log.error(f"[analyst] Remote generation failed, falling back to local: {e}")

        if not self._load_model():
            return None

        try:
            prompt = prompt or ""
            system_prompt = system_prompt or ""
            # Enforce literary language
            if (
                "makedonski" not in system_prompt.lower()
                and "srpskom" not in system_prompt.lower()
                and "srpski" not in system_prompt.lower()
            ):
                if lang == "sr":
                    lang_constraint = (
                        "Zboruvaj ISKLUCIVO na srpskom jeziku (ekavica). Koristi srpsku gramatiku i vokabular."
                    )
                else:
                    lang_constraint = "Zboruvaj ISKLUCIVO na standarden literaturen makedonski jazik. ZABRANETO e koristenje na bugarski, srpski ili hrvatski zborovi ili formi."
                system_prompt = f"{lang_constraint} {system_prompt}"

            if len(prompt) > MAX_PROMPT_CHARS:
                if lang == "sr":
                    trunc_msg = "\n\n[Kontekst je skraćen za lokalni model.]"
                else:
                    trunc_msg = "\n\n[Kontekstot e skraten za lokalniot model.]"
                prompt = prompt[:MAX_PROMPT_CHARS] + trunc_msg

            # Gemma 2 Instruct format (optimized for a single user turn).
            full_prompt = f"<start_of_turn>user\n{system_prompt}\n\n{prompt}<end_of_turn>\n<start_of_turn>model\n"

            # Set grammar dynamically based on response_schema
            local_grammar = None
            if response_schema:
                try:
                    schema_json = json.dumps(response_schema.model_json_schema())
                    local_grammar = LlamaGrammar.from_json_schema(schema_json)
                except Exception as e:
                    log.error(f"[analyst] Failed to compile grammar from schema: {e}")
                    local_grammar = self.grammar
            elif use_grammar:
                local_grammar = self.grammar

            output = self.model(
                full_prompt,
                max_tokens=max_tokens,
                stop=["<end_of_turn>", "<eos>", "###"],
                echo=False,
                temperature=0.1,  # Low temperature for analytical consistency
                grammar=local_grammar,
            )
            return output["choices"][0]["text"].strip()
        except Exception as e:
            log.error(f"[analyst] Generation failed: {e}")
            return None

    def normalize_headline(self, title: str, lang: str = "mk") -> str:
        """Converts sensationalist headlines to literary/broadsheet style."""
        if lang == "sr":
            system = (
                "Ti si iskusni urednik u ozbiljnim srpskim novinama. "
                "Pretvori naslov u književni, neutralan i informativan stil. "
                "Ukloni senzacionalizam, uzvičnike i klikbejt reči kao što su 'ŠOK', 'SKANDAL', 'EVO ŠTA'. "
                "Vrati samo jedan pročišćen naslov na srpskom jeziku.\n\n"
                "PRIMER:\n"
                "Ulaz: ŠOKANTNO: Vučić razneo opoziciju ovom izjavom!!!\n"
                "Izlaz: Vučić uputio kritike opozicionim strankama"
            )
        else:
            system = (
                "Ti si iskusen urednik vo makedonski seriozen vesnik. "
                "Pretvori ga naslovot vo literaturen, neutralen i informativen stil. "
                "Otstrani senzacionalizam, izvicnici i klikbejt zborovi kako 'SOK', 'SKANDAL', 'EVE STO'. "
                "Vrati samo eden procisten naslov na makedonski jazik.\n\n"
                "PRIMER:\n"
                "Vlez: SOKANTNO: Mickoski me raznese opozicijata so ova izjava!!!\n"
                "Izlez: Mickoski upati kritiki do opoziciskite partii"
            )
        result = self.analyze(f"Naslov: {title}", system, max_tokens=64, lang=lang)
        return result if result else title

    def extract_deep_metadata(self, text: str, lang: str = "mk") -> Dict[str, Any]:
        """Extracts facts and pulse from text."""
        if lang == "sr":
            system = (
                "Analiziraj tekst na srpskom jeziku i vrati JSON sa sledećim poljima: "
                "'facts' (lista od 3 ključna fakta), 'entities' (lista imena i institucija), "
                "'sentiment' (pozitivan, negativan ili neutralan), 'pulse' (od 1 do 100 važnost). "
                "Vrati samo čist JSON.\n\n"
                "PRIMER:\n"
                "Ulaz: Vlada je danas odlučila da poveća penzije za 5 procenata počevši od septembra...\n"
                'Izlaz: {"facts": ["Povećanje penzija za 5%", "Mera stupa na snagu od septembra", "Odluka Vlade"], "entities": ["Vlada"], "sentiment": "pozitivan", "pulse": 75}'
            )
        else:
            system = (
                "Analiziraj ga tekstot na makedonski jazik i vrati JSON so slednite polinja: "
                "'facts' (lista od 3 klucni fakti), 'entities' (lista od iminja i institucii), "
                "'sentiment' (pozitiven, negativen ili neutralen), 'pulse' (od 1 do 100 vaznost). "
                "Vrati samo cist JSON.\n\n"
                "PRIMER:\n"
                "Vlez: Vladata danas odluci da im zgolemi penziite za 5 procenti pocnuvajci od septembar...\n"
                'Izlez: {"facts": ["Zgolemuvanje na penziite za 5%", "Merkata stapuva na sila od septembar", "Odluka na Vladata"], "entities": ["Vlada"], "sentiment": "pozitiven", "pulse": 75}'
            )
        raw = self.analyze(text[:1500], system, max_tokens=400, response_schema=DeepMetadataResponse, lang=lang)
        if not raw:
            return {"error": "no_response"}

        try:
            parsed = json.loads(raw)
            return DeepMetadataResponse(**parsed).model_dump()
        except Exception as e:
            log.error(f"[analyst] JSON/Pydantic parse failed: {e} | Raw: {raw[:100]}...")
            return {"error": "failed_to_parse"}

    def assess_pluralism(self, titles_with_sources: List[str], lang: str = "mk") -> Dict[str, Any]:
        """Analyzes if a cluster represents a diverse consensus or an echo chamber."""
        if lang == "sr":
            system = (
                "Ti si ekspert za medijski pluralizam. Analiziraj diverzitet izvora i naslova. "
                "Budi veoma strog. Ako su svi izvori iz iste grupe ili imaju isti naslov, daj nizak skor (ispod 40). "
                "Ako ima različitih perspektiva (npr. pro-vladini i opozicioni izvori), daj visok skor (iznad 70).\n\n"
                "Vrati ISKLJUČIVO JSON objekat sa sledećim ključnim rečima:\n"
                "- 'score': ceo broj od 0 do 100\n"
                "- 'verdict': kratka rečenica na srpskom koja objašnjava skor\n"
                "- 'bias_detected': tačno/netačno (boolean)\n\n"
                "Primer za 'verdict': 'Visok pluralizam sa raznovrsnim izvorima i suprotstavljenim stavovima.'\n"
            )
        else:
            system = (
                "Ti si ekspert za mediumski pluralizam. Analiziraj ga diverzitetot na izvorite i naslovite. "
                "Bidi mnogu strog. Ako site izvori se od ista grupa ili imaat ist naslov, daj nizok skor (pod 40). "
                "Ako ima razliciti perspektivi (na pr. pro-vladini i opoziciski izvori), daj visok skor (nad 70).\n\n"
                "Vrati ISKLUCIVO JSON objekt so slednite klucni zborovi:\n"
                "- 'score': cel broj od 0 do 100\n"
                "- 'verdict': kratka recenica na makedonski koja ga objasnuva skorot\n"
                "- 'bias_detected': tocno/netocno (boolean)\n\n"
                "Primer za 'verdict': 'Visok pluralizam so raznovidni izvori i sprotivstaveni stavovi.'\n"
            )
        prompt = "ANALIZIRAJ OVE IZVORE:\n" if lang == "sr" else "ANALIZIRAJ im OVIE izvori:\n"
        prompt += "\n".join(titles_with_sources)
        raw = self.analyze(prompt, system, max_tokens=256, response_schema=PluralismResponse, lang=lang)
        fallback = {
            "score": 50,
            "verdict": "Standardna pokrivenost" if lang == "sr" else "Standardna pokrienost",
            "bias_detected": False,
        }
        if not raw:
            return fallback

        try:
            parsed = json.loads(raw)
            return PluralismResponse(**parsed).model_dump()
        except Exception as e:
            log.debug(f"JSON parse error in assess_pluralism: {e}")
            return fallback

    def detect_echo(self, article_text: str, cluster_context: str, lang: str = "mk") -> float:
        """Detects if an article is a unique report or just a 'copy-paste' (echo)."""
        if lang == "sr":
            system = (
                "Uporedi tekst sa kontekstom. Da li donosi nove informacije ili je samo prepisano? "
                "Vrati samo brojku od 0.0 (potpuna kopija) do 1.0 (potpuno unikatno)."
            )
        else:
            system = (
                "Sporedi ga tekstot so kontekstot. Dali nosi novi informacii ili e samo prepisano? "
                "Vrati samo brojka od 0.0 (celosna kopija) do 1.0 (celosno unikatno)."
            )
        prompt = f"TEKST: {article_text[:500]}\nKONTEKST: {cluster_context[:1000]}"
        result = self.analyze(prompt, system, max_tokens=10, lang=lang)
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

    def research_query(self, query: str, context: str, lang: str = "mk") -> Dict[str, Any]:
        """Acts as a local researcher providing cited answers and follow-up suggestions."""
        if lang == "sr":
            system = (
                "Ti si Presek Istraživač. Odgovori na pitanje koristeći isključivo dati kontekst iz medija. "
                "1. Za svaki ključni fakt ili brojku, navedi ime medija u kvadratnim zagradama, na primer: [RTS]. "
                "2. Na kraju odgovora, generiši tačno 3 predlog-pitanja za sledeće istraživanje povezana sa ovom temom. "
                "Vrati odgovor u JSON formatu sa poljima: 'answer' (tekst sa citatima) i 'suggestions' (lista od 3 pitanja).\n\n"
                "PRIMER:\n"
                "Ulaz: Koliki je najavljeni iznos pomoći?\\nKontekst: [RTS] Vlada je izdvojila 10 miliona evra...\n"
                'Izlez: {"answer": "Vlada je najavila pomoć u iznosu od 10 miliona evra [RTS].", "suggestions": ["Kada će se isplatiti pomoć?", "Ko ispunjava kriterijume?", "Kakav je efekat na budžet?"]}'
            )
        else:
            system = (
                "Ti si Presek Istrazuvac. odgovori na prasanjeto koristejci ga samo dadeniot kontekst od makedonskite mediumi. "
                "1. Za sekoj klucen fakt ili brojka, navedi ga imeto na mediumot vo kvadratni zagradi, na primer: [Sitel]. "
                "2. Na krajot od odgovorot, generiraj tocno 3 predlog-prasanja za sledece istrazuvanje povrzani so ova tema. "
                "Vrati ga odgovorot vo JSON format so polinja: 'answer' (tekst so citati) i 'suggestions' (lista od 3 prasanja).\n\n"
                "PRIMER:\n"
                "Vlez: Koj e najaveniot iznos za pomos?\\nKontekst: [MTV] Vladata izdvoi 10 milioni evra...\n"
                'Izlez: {"answer": "Vladata najavi pomos vo iznos od 10 milioni evra [MTV].", "suggestions": ["Koga ce se isplati pomosta?", "Koj im ispolnuva kriteriumite?", "Kakov e efektot vrz budzetot?"]}'
            )
        prompt = f"PITANJE: {query}\nKONTEKST: {context}" if lang == "sr" else f"PRASANjE: {query}\nKONTEKST: {context}"
        raw = self.analyze(prompt, system, max_tokens=800, response_schema=ResearchQueryResponse, lang=lang)

        fallback = {
            "answer": raw if raw else ("Nema dovoljno informacija." if lang == "sr" else "Nema dovolno informacii."),
            "suggestions": [
                "Koji su ključni akteri?" if lang == "sr" else "Koi se klucnite akteri?",
                "Kakav je ekonomski efekat?" if lang == "sr" else "Kakov e ekonomskiot efekt?",
                "Koji su sledeći koraci?" if lang == "sr" else "Koi se slednite cekori?",
            ],
        }
        if not raw:
            return fallback

        try:
            parsed = json.loads(raw)
            return ResearchQueryResponse(**parsed).model_dump()
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            log.debug(f"JSON/Pydantic parse error in research_query: {e}")
            return fallback


# Singleton instance
analyst = LocalAnalyst()
