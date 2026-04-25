import os
import logging
import json
import time
from typing import Optional, Dict, Any
from llama_cpp import Llama

log = logging.getLogger("presek.analyst")

# Config for Gemma 2 2B on 2-core CPU
MODEL_PATH = os.environ.get("LOCAL_MODEL_PATH", "models/gemma-2-2b-it-Q4_K_M.gguf")
N_THREADS = int(os.environ.get("MODEL_THREADS", "2")) 

class LocalAnalyst:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LocalAnalyst, cls).__new__(cls)
            cls._instance.model = None
        return cls._instance

    def _load_model(self):
        if self.model is not None:
            return True
        
        if not os.path.exists(MODEL_PATH):
            log.warning(f"Local model not found at {MODEL_PATH}. Deep Local tasks will be skipped.")
            return False

        try:
            t0 = time.time()
            # Optimized for 6GB RAM: small context window, limited threads
            self.model = Llama(
                model_path=MODEL_PATH,
                n_ctx=2048, 
                n_threads=N_THREADS,
                verbose=False
            )
            log.info(f"[analyst] Gemma 2 2B loaded in {time.time()-t0:.1f}s")
            return True
        except Exception as e:
            log.error(f"[analyst] Failed to load local model: {e}")
            return False

    def analyze(self, prompt: str, system_prompt: str, max_tokens: int = 512) -> Optional[str]:
        if not self._load_model():
            return None

        try:
            # Gemma 2 Instruct format
            full_prompt = f"<start_of_turn>user\n{system_prompt}\n\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
            
            output = self.model(
                full_prompt,
                max_tokens=max_tokens,
                stop=["<end_of_turn>", "###"],
                echo=False
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
            "Врати само еден прочистен наслов на македонски јазик."
        )
        result = self.analyze(f"Наслов: {title}", system, max_tokens=64)
        return result if result else title

    def assess_pluralism(self, titles_with_sources: List[str]) -> Dict[str, Any]:
        """Analyzes if a cluster represents a diverse consensus or an echo chamber."""
        system = (
            "Ти си медиумски аналитичар. Анализирај ги овие наслови и извори од Македонија. "
            "Врати JSON со: 'score' (0-100), 'verdict' (краток опис на македонски), "
            "'bias_detected' (дали сите извори се од иста група/страна)."
        )
        prompt = "\n".join(titles_with_sources)
        raw = self.analyze(prompt, system, max_tokens=256)
        try:
            return json.loads(raw)
        except:
            return {"score": 50, "verdict": "Стандардна покриеност"}

    def detect_echo(self, article_text: str, cluster_context: str) -> float:
        """Detects if an article is a unique report or just a 'copy-paste' (echo)."""
        system = (
            "Спореди го текстот со контекстот. Дали носи нови информации или е само препишано? "
            "Врати само бројка од 0.0 (целосна копија) до 1.0 (целосно уникатно)."
        )
        prompt = f"ТЕКСТ: {article_text[:500]}\nКОНТЕКСТ: {cluster_context[:1000]}"
        result = self.analyze(prompt, system, max_tokens=10)
        try:
            return float(re.findall(r"[\d.]+", result)[0])
        except:
            return 1.0

    def research_query(self, query: str, context: str) -> str:
        """Acts as a local researcher answering user questions based on cluster data."""
        system = (
            "Ти си Пресек Истражувач. Одговори на прашањето користејќи го само дадениот контекст од македонските медиуми. "
            "Биди објективен, професионален и концизен. Ако нема информација, кажи дека не е познато."
        )
        prompt = f"ПРАШАЊЕ: {query}\nКОНТЕКСТ: {context}"
        return self.analyze(prompt, system, max_tokens=512)

# Singleton instance
analyst = LocalAnalyst()
