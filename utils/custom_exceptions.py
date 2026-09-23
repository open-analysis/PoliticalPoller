class UnableToFindBaseUrlError(Exception):
    def __init__(self, message, url, domain_names):
        super().__init__(message)
        self.message = message
        self.url = url
        self.domain_names = domain_names

    def __str__(self):
        return f"Base URL not found in {self.url} based on domain name list {self.domain_names}\n\t{self.message}"
