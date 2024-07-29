class LinkBioBan(Exception):
    pass


class BadChatLink(Exception):
    def __init__(self, link):
        super().__init__('Bad chat link {}'.format(link))
        self.chat_link = link
