"""Stub: audio service removed in mk-only simplify."""


class AudioService:
    def __init__(self, *a, **kw):
        pass

    async def generate_audio(self, *a, **kw):
        return None

    async def generate_cluster_audio(self, *a, **kw):
        return None

    @staticmethod
    def get_cluster_audio_path_and_url(*a, **kw):
        return "", None


def select_cluster_audio_text(*a, **kw):
    return ""
