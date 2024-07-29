import random
import re


class MessageGenerator:
    def __init__(self, templates_file_path: str):
        self._templates_file_path = templates_file_path
        with open(templates_file_path, "r", encoding="utf-8") as f:
            templates = f.readlines()
            self._templates = [template.strip() for template in templates if template.strip() and not template.startswith("#")]
        self._pattern = re.compile(r'\{([^}]+)\}')

    def generate_random_msg(self):
        choice = random.choice(self._templates)
        last_end = 0
        phrase = []
        for match in self._pattern.finditer(choice):
            phrase.append(choice[last_end:match.start()])

            options = match.group(1).split('|')
            phrase.append(random.choice(options))

            last_end = match.end()
        phrase.append(choice[last_end:])
        return "".join(phrase)


    async def generate_ai_response(self, text):
        ...


if __name__ == '__main__':
    generator = MessageGenerator(templates_file_path=r'C:\Users\Dmitry\Home\Programming\PytonProjects\Payment_projects\07_2024\tg_orders\pervonax\data\mailing.txt')
    msg = generator.generate_random_msg()
    print(msg)
