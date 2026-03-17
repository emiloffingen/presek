import json, urllib.request

class BreakingNewsNotifier:
    def __init__(self, topic, threshold=3):
        self.topic     = topic
        self.threshold = threshold
        self._notified = set()  # avoid re-notifying same cluster in same session

    def send(self, title, message):
        try:
            data = {
                "topic":   self.topic,
                "title":   title,
                "message": message,
                "tags":    ["newspaper"],
                "priority": 4,
            }
            req = urllib.request.Request(
                "https://ntfy.sh",
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"[notifier] Error: {e}")

    def check_and_notify(self, clusters):
        for c in clusters:
            arts = c.get("articles", [])
            cid  = c.get("cluster_id") or (arts[0].get("cluster_id") if arts else None)
            if not arts or not cid:
                continue
            if len(arts) >= self.threshold and cid not in self._notified:
                headline = arts[0].get("title", "")
                sources  = len({a.get("source") for a in arts})
                self.send(
                    "Пресек — Важна вест",
                    f"{headline}\n{sources} извори известуваат"
                )
                self._notified.add(cid)
