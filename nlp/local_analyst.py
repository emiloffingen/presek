import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _import_llama_cpp():
    """Lazy import so API processes without llama-cpp can still use zero-token helpers."""
    try:
        from llama_cpp import Llama, LlamaGrammar

        return Llama, LlamaGrammar
    except ImportError:
        return None, None

try:
    from core.config import SOURCE_CATEGORIES
except ImportError:
    SOURCE_CATEGORIES = {}

TIER_MAP = {
    "Agencijski": "Mainstream",
    "Javni servis": "Mainstream",
    "Javni Servis": "Mainstream",
    "glavni": "Mainstream",
    "Nezavisni": "Independent",
    "Istraživački": "Independent",
    "Regionalni": "Regional/Alt",
    "Alternativni": "Regional/Alt",
    "Lokalni": "Regional/Alt",
    "Tabloidi": "Tabloid"
}


log = logging.getLogger("presek.analyst")

# Config for Gemma 4 E2B on 8-core CPU (utilizing 6 threads)
MODEL_PATH = os.environ.get("LOCAL_MODEL_PATH", "models/gemma-4-E2B-it-Q4_K_M.gguf")
N_THREADS = int(os.environ.get("MODEL_THREADS", "6"))
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
                cls._instance._grammar = None
                cls._instance._grammar_compiled = False
        return cls._instance

    @property
    def grammar(self):
        if not self._grammar_compiled:
            _, LlamaGrammar = _import_llama_cpp()
            if LlamaGrammar is not None:
                try:
                    self._grammar = LlamaGrammar.from_string(JSON_GBNF)
                except Exception as e:
                    log.error(f"[analyst] Failed to compile grammar: {e}")
                    self._grammar = None
            else:
                self._grammar = None
            self._grammar_compiled = True
        return self._grammar

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

            Llama, _ = _import_llama_cpp()
            if Llama is None:
                log.warning("[analyst] llama_cpp is not installed; local model inference is unavailable.")
                return False

            try:
                t0 = time.time()
                # Keep enough context for fallback brief/synthesis while staying within small-host RAM limits.
                use_mlock = os.environ.get("LOCAL_MODEL_USE_MLOCK", "true").lower() == "true"
                self.model = Llama(
                    model_path=MODEL_PATH,
                    n_ctx=MODEL_CONTEXT,
                    n_threads=N_THREADS,
                    use_mlock=use_mlock,
                    verbose=False,
                )
                model_filename = os.path.basename(MODEL_PATH)
                if "gemma-4" in model_filename.lower():
                    model_display = "Gemma 4 E2B"
                else:
                    model_display = model_filename
                log.info(f"[analyst] {model_display} loaded in {time.time()-t0:.1f}s")
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
        temperature: Optional[float] = None,
        force_local: bool = False,
        lock_timeout: int | None = None,
        task_type: str = "default",
    ) -> Optional[str]:
        # Try remote API first if enabled (default True)
        if not force_local and os.environ.get("USE_REMOTE_ANALYST", "true").lower() == "true":
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

        # Acquire Redis lock with token verification to prevent concurrent CPU-heavy llama-cpp generation
        import uuid

        from utils import redis_client

        lock_key = "lock:local_llm_synthesis" if task_type == "synthesis" else "lock:local_llm_inference"
        if lock_timeout is None:
            if task_type == "synthesis":
                from core.runtime_limits import LOCAL_LLM_SYNTHESIS_LOCK_TIMEOUT_SECONDS

                lock_timeout = LOCAL_LLM_SYNTHESIS_LOCK_TIMEOUT_SECONDS
            else:
                from core.runtime_limits import LOCAL_LLM_LOCK_TIMEOUT_SECONDS

                lock_timeout = LOCAL_LLM_LOCK_TIMEOUT_SECONDS
        lock_token = str(uuid.uuid4())
        acquired = False
        start_time = time.time()

        while time.time() - start_time < lock_timeout:
            try:
                if redis_client.set(lock_key, lock_token, nx=True, ex=600):  # Lock expires in 600 seconds
                    acquired = True
                    break
            except Exception as e:
                log.debug(f"[analyst] Redis inference lock error: {e}")
            time.sleep(1.0)

        if not acquired:
            log.warning(
                "[analyst] Could not acquire local LLM lock (%s) within %ss, skipping task.",
                lock_key,
                lock_timeout,
            )
            return None

        try:
            if not self._load_model():
                return None

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

            # Gemma instruct format (optimized for a single user turn).
            full_prompt = f"<start_of_turn>user\n{system_prompt}\n\n{prompt}<end_of_turn>\n<start_of_turn>model\n"

            # Set grammar dynamically based on response_schema
            local_grammar = None
            if response_schema:
                try:
                    _, LlamaGrammar = _import_llama_cpp()
                    if LlamaGrammar is None:
                        raise ImportError("llama_cpp is not installed")
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
                temperature=0.1 if temperature is None else temperature,
                grammar=local_grammar,
            )
            return output["choices"][0]["text"].strip()
        except Exception as e:
            log.error(f"[analyst] Generation failed: {e}")
            return None
        finally:
            if acquired:
                try:
                    current_val = redis_client.get(lock_key)
                    val_str = current_val.decode() if isinstance(current_val, bytes) else str(current_val or "")
                    if val_str == lock_token:
                        redis_client.delete(lock_key)
                except Exception as e:
                    log.debug(f"[analyst] Redis unlock error: {e}")

    def de_shout(self, text: str) -> str:
        """Converts completely uppercase headlines or shouting words to sentence case."""
        if not text:
            return ""
        alpha_chars = [c for c in text if c.isalpha()]
        if alpha_chars:
            upper_count = sum(1 for c in alpha_chars if c.isupper())
            if upper_count / len(alpha_chars) > 0.6 and len(alpha_chars) > 4:
                return text.lower()
        return text

    def get_zero_token_normalized_headline(self, title: str, lang: str = "mk") -> str:
        """Converts sensationalist headlines to literary/broadsheet style zero-token."""
        title = title or ""
        
        # 1. De-shout completely uppercase headlines
        title = self.de_shout(title)
        
        # 2. Clean leading/trailing/inline bracketed tabloid noise e.g. [FOTO], (VIDEO)
        bracket_rx = r'(?i)\s*[\[\(](foto|video|uživo|uzivo|ekskluzivno|detalji|analiza|galerija|slobodno|live|breaking|reakcija|saopštenje|saopstenje|soopstenie|foto/video)[\]\)]\s*'
        title = re.sub(bracket_rx, ' ', title)
        
        # 3. Clean exclamation marks and excessive question marks
        title = re.sub(r'!+', '', title)
        title = re.sub(r'\?{2,}', '?', title)
        
        # 4. Clean clickbait prefix patterns (case-insensitive)
        clickbait_words = [
            "šokantno", "sokantno", "šok", "sok", "skandalozno", "skandal", 
            "bomba", "hitno", "drama", "neverovatno", "neverojatno", "ekskluzivno", 
            "užas", "uzas", "haos", "pakao", "neviđeno", "nevidno", "procurilo", 
            "senzacionalno", "skršil", "skrsil", "poludeo", "zapanjio", "otkrio", 
            "nećete verovati", "nema da veruvate", "grom", "vrisak", "panika", 
            "vanredno", "spektakularno", "evo šta", "evo sta", "eve što", "eve sto"
        ]
        clickbait_rx = r'(?i)\b(' + '|'.join(clickbait_words) + r')\b\s*[:\-]?\s*'
        title = re.sub(clickbait_rx, '', title)
        
        # Strip surrounding spaces and punctuation leftovers
        title = title.strip(" :-\t\n\r|.")
        
        # Ensure first letter is capitalized
        if title:
            title = title[0].upper() + title[1:]
            return title
        return title

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
        try:
            result = self.analyze(f"Naslov: {title}", system, max_tokens=64, lang=lang)
            if result:
                return result
        except Exception as e:
            log.error(f"[analyst] Headline normalization LLM failed: {e}")
            
        return self.get_zero_token_normalized_headline(title, lang=lang)


    def get_zero_token_metadata(self, text: str, lang: str = "mk") -> Dict[str, Any]:
        """Extracts facts, entities, sentiment, and pulse using zero-token regex heuristics."""
        text = text or ""
        
        # 1. Facts Extraction
        sentences = re.split(r'(?<=[.!?])\s+', text)
        clean_sentences = []
        for s in sentences:
            s_clean = s.strip()
            # Exclude URLs, very short lines, or lines containing mostly special characters
            if len(s_clean) > 15 and not s_clean.startswith(('http', 'www')) and not s_clean.startswith('NASLOV:'):
                clean_sentences.append(s_clean)
                
        if len(clean_sentences) < 3:
            # Fallback to splitting by comma or semicolon
            for s in sentences:
                for part in re.split(r'[,;]', s):
                    part_clean = part.strip()
                    if len(part_clean) > 15 and part_clean not in clean_sentences and not part_clean.startswith('NASLOV:'):
                        clean_sentences.append(part_clean)
                        
        while len(clean_sentences) < 3:
            if lang == "sr":
                clean_sentences.append(f"Važan detalj o analiziranom medijskom izveštaju {len(clean_sentences)+1}")
            else:
                clean_sentences.append(f"Važen detal za analiziraniot mediumski izveštaj {len(clean_sentences)+1}")
                
        facts = [f[:150] for f in clean_sentences[:3]]
        
        # 2. Entities Extraction
        # Match capitalized words/phrases in cyrillic & latin
        pattern = r'\b[A-ZŠĐČĆŽА-ЯЃЌЅЏЉЊ][a-zšđčćžа-яѓќѕџљњ]*(?:\s+[A-ZŠĐČĆŽА-ЯЃЌЅЏЉЊ][a-zšđčćžа-яѓќѕџљњ]*)*\b'
        candidates = re.findall(pattern, text)
        
        stopwords = {
            "Vo", "Na", "Za", "I", "No", "Se", "So", "Da", "Koga", "Kaj", "Ova", "Toa", "Tie", "Nie", "Vie", "Sekogash", "Ama",
            "U", "Ali", "Sa", "Kada", "Kod", "Ovo", "To", "Oni", "Mi", "Vi", "Ako", "Jer", "Dok",
            "The", "A", "An", "In", "On", "At", "For", "To", "With", "By", "NASLOV", "TEKST"
        }
        
        entities = []
        seen = set()
        for cand in candidates:
            cand_clean = cand.strip()
            if not cand_clean or len(cand_clean) < 2:
                continue
            if cand_clean in stopwords:
                continue
            if re.match(r'^\d+$', cand_clean):
                continue
            cand_lower = cand_clean.lower()
            if cand_lower not in seen:
                seen.add(cand_lower)
                entities.append(cand_clean)
                
        entities = entities[:10]
        if not entities:
            entities = ["Vlada" if lang != "sr" else "Vlada"]
            
        # 3. Sentiment Estimation
        pos_words = ["uspeh", "odlic", "poveka", "zgolem", "dobr", "razvoj", "sorabot", "poddr", "napred", "poveća", "uspeš", "stabilan", "stabilen"]
        neg_words = ["sukob", "kriz", "pad", "napad", "problem", "optuz", "skandal", "smrt", "nesrec", "katastrof", "poraz", "obvin", "optuž", "nesreć", "korupcija", "hronika"]
        
        text_lower = text.lower()
        pos_count = sum(text_lower.count(w) for w in pos_words)
        neg_count = sum(text_lower.count(w) for w in neg_words)
        
        if pos_count > neg_count:
            sentiment = "pozitivan" if lang == "sr" else "pozitiven"
        elif neg_count > pos_count:
            sentiment = "negativan" if lang == "sr" else "negativen"
        else:
            sentiment = "neutralan" if lang == "sr" else "neutralen"
            
        # 4. Pulse Calculation
        pulse = 50
        pulse += min(len(entities) * 5, 20)
        high_profile = ["vlada", "mickoski", "vucic", "vučić", "sobranie", "skupstina", "skupština", "pretsedatel", "precednik", "izbori"]
        if any(hp in text_lower for hp in high_profile):
            pulse += 15
        if re.search(r'\d+', text):
            pulse += 10
        if "%" in text or "procent" in text:
            pulse += 5
            
        pulse = max(10, min(95, pulse))
        
        return {
            "facts": facts,
            "entities": entities,
            "sentiment": sentiment,
            "pulse": pulse
        }

    def get_zero_token_pluralism(self, titles_with_sources: List[str], lang: str = "mk") -> Dict[str, Any]:
        """Analyzes media source pluralism using TIER_MAP and SOURCE_CATEGORIES zero-token heuristics."""
        tiers_present = set()
        
        for item in titles_with_sources:
            source = "Lokalni"
            # Try splitting by colon
            if ":" in item:
                src_part = item.split(":", 1)[0].strip()
                if src_part:
                    source = src_part
            else:
                # Try finding matching keys in SOURCE_CATEGORIES as a substring
                item_lower = item.lower()
                matched = False
                for k in SOURCE_CATEGORIES.keys():
                    if k.lower() in item_lower:
                        source = k
                        matched = True
                        break
                if not matched:
                    # Look inside parentheses
                    match = re.search(r'\(([^)]+)\)[^()]*$', item)
                    if match:
                        source = match.group(1).strip()
            
            # Map source to category and tier
            cat = SOURCE_CATEGORIES.get(source, "Lokalni")
            tier = TIER_MAP.get(cat, "Regional/Alt")
            tiers_present.add(tier)
            
        num_tiers = len(tiers_present)
        
        if num_tiers >= 3:
            score = 85
            verdict = (
                "Visok medijski pluralizam sa širokom zastupljenošću različitih medijskih grupa i perspektiva."
                if lang == "sr"
                else "Visok mediumski pluralizam so široka zastupenost na razlicni mediumski grupi i perspektivi."
            )
            bias_detected = False
        elif num_tiers == 2:
            score = 65
            verdict = (
                "Umeren medijski pluralizam sa uočenom ravnotežom između različitih medijskih grupa."
                if lang == "sr"
                else "Umeren mediumski pluralizam so uocena ramnoteza megu razlicni mediumski grupi."
            )
            bias_detected = False
        else:
            score = 35
            verdict = (
                "Nizak medijski pluralizam. Izveštavanje je jednostrano i dominira samo jedna perspektiva (echo chamber)."
                if lang == "sr"
                else "Nizok mediumski pluralizam. Izvestuvanjeto e ednostrano i dominira samo edna perspektiva (echo chamber)."
            )
            bias_detected = True
            
        return {
            "score": score,
            "verdict": verdict,
            "bias_detected": bias_detected
        }

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
        
        try:
            raw = self.analyze(text[:1500], system, max_tokens=400, response_schema=DeepMetadataResponse, lang=lang, lock_timeout=5)
            if raw:
                parsed = json.loads(raw)
                return DeepMetadataResponse(**parsed).model_dump()
        except Exception as e:
            log.error(f"[analyst] LLM/Pydantic metadata generation failed, falling back: {e}")

        # Fallback to zero-token heuristics
        log.info("[analyst] Running zero-token metadata extraction fallback.")
        try:
            fallback_data = self.get_zero_token_metadata(text, lang=lang)
            return DeepMetadataResponse(**fallback_data).model_dump()
        except Exception as fe:
            log.error(f"[analyst] Zero-token metadata fallback failed: {fe}")
            return {
                "facts": ["Analiza u toku" if lang == "sr" else "Analiza vo tek", "Nije moguće ekstrahovati podatke" if lang == "sr" else "Ne e vozmozno da se ekstrahiraat podatoci", "Sistemski podaci" if lang == "sr" else "Sistemski podatoci"],
                "entities": ["Sistem" if lang == "sr" else "Sistem"],
                "sentiment": "neutralan" if lang == "sr" else "neutralen",
                "pulse": 50
            }

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
        
        try:
            raw = self.analyze(prompt, system, max_tokens=256, response_schema=PluralismResponse, lang=lang, lock_timeout=5)
            if raw:
                parsed = json.loads(raw)
                return PluralismResponse(**parsed).model_dump()
        except Exception as e:
            log.debug(f"LLM pluralism assessment failed, falling back: {e}")

        # Fallback to zero-token heuristics
        log.info("[analyst] Running zero-token pluralism assessment fallback.")
        try:
            fallback_data = self.get_zero_token_pluralism(titles_with_sources, lang=lang)
            return PluralismResponse(**fallback_data).model_dump()
        except Exception as fe:
            log.error(f"[analyst] Zero-token pluralism fallback failed: {fe}")
            return {
                "score": 50,
                "verdict": "Standardna pokrivenost" if lang == "sr" else "Standardna pokrienost",
                "bias_detected": False,
            }


    def get_zero_token_echo(self, article_text: str, cluster_context: str) -> float:
        """Estimates originality (0.0 to 1.0) using word overlap zero-token similarity."""
        article_text = article_text or ""
        cluster_context = cluster_context or ""
        
        # Tokenize into unique words (ignoring case and short words)
        def get_words(t):
            # Extract Cyrillic and Latin words
            return set(re.findall(r'\b[A-Za-zА-Яа-яŠĐČĆŽšđčćžЃЌЅЏЉЊѓќѕџљњ]{3,}\b', t.lower()))
            
        words_art = get_words(article_text)
        words_ctx = get_words(cluster_context)
        
        if not words_art or not words_ctx:
            return 1.0
            
        # Jaccard similarity = intersection / union
        intersection = words_art.intersection(words_ctx)
        union = words_art.union(words_ctx)
        similarity = len(intersection) / len(union)
        
        # Map similarity to originality smoothly:
        # If similarity >= 0.4, it's highly likely to be a copy-paste/echo (0.0 originality)
        # If similarity is 0.0, it's 1.0 (completely unique)
        originality = max(0.0, min(1.0, 1.0 - (similarity / 0.4)))
        return round(originality, 2)

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
        
        try:
            result = self.analyze(prompt, system, max_tokens=10, lang=lang)
            if result:
                matches = re.findall(r"[\d.]+", result)
                if matches:
                    return float(matches[0])
        except Exception as e:
            log.error(f"[analyst] Echo detection LLM failed, falling back: {e}")
            
        # Fallback to zero-token heuristic
        return self.get_zero_token_echo(article_text, cluster_context)


    def research_query(
        self,
        query: str,
        context: str,
        lang: str = "mk",
        force_local: bool = False,
    ) -> Dict[str, Any]:
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
        raw = self.analyze(
            prompt,
            system,
            max_tokens=800,
            response_schema=ResearchQueryResponse,
            lang=lang,
            lock_timeout=15,
            force_local=force_local,
        )

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
