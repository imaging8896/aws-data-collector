from parser import NewsHTMLParser


class GeneralNewsHTMLParser(NewsHTMLParser):

    def __init__(self, *, convert_charrefs: bool = True) -> None:
        super().__init__(convert_charrefs=convert_charrefs)

        self._entering_article = False
        self._entering_p = False

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            self._entering_article = True
        elif self._entering_article:
            if tag == "p":
                self._entering_p = True
                self.has_content_section = True

    def handle_endtag(self, tag):
        if tag == "article":
            self._entering_article = False
        elif tag == "p":
            self._entering_p = False

    def handle_data(self, data):
        if self._entering_article and self._entering_p:
            if stripped_data := data.strip():
                self._content += stripped_data + "\n"
