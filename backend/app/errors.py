class ProviderError(Exception):
    """Erreur venant d'un fournisseur de donnees, avec un type que l'interface sait afficher."""

    HTTP = {"quota": 429, "payant": 403, "inconnu": 404, "reseau": 502, "config": 500}

    def __init__(self, kind, provider, message):
        super().__init__(message)
        self.kind = kind
        self.provider = provider
        self.message = message

    @property
    def status(self):
        return self.HTTP.get(self.kind, 502)
