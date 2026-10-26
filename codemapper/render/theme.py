"""Shared look of every document: landscape A4, one palette, one type scale, the author in the metadata."""
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors

PAGE = landscape(A4)
MARGIN = 28
FONT, BOLD, MONO = 'Helvetica', 'Helvetica-Bold', 'Courier'

INK = colors.HexColor('#1F2328')
MUTED = colors.HexColor('#5B6470')
ACCENT = colors.HexColor('#14463A')       # headings, title bar
HEAD = colors.HexColor('#1F3864')         # table headers
RULE = colors.HexColor('#C9CED6')
ZEBRA = colors.HexColor('#F4F6F8')

# node fills (functional flow) - border is a darker shade of the same hue
NODE = {
    'start': ('#E3EEF9', '#2F6DB5'), 'end': ('#E3EEF9', '#2F6DB5'),
    'access': ('#FDECEC', '#B23B3B'), 'input': ('#EEF2F7', '#5B6B82'),
    'form': ('#EAF5EC', '#2E7D4F'), 'dropdown': ('#F1F8E9', '#558B2F'),
    'decision': ('#FFF4DB', '#B7791F'), 'call': ('#F3EEFA', '#6B4AA0'),
    'data': ('#E6F4F4', '#1F7A7A'), 'middle': ('#FCEFE3', '#B5602F'),
    'message': ('#FFF0F3', '#B0306A'), 'output': ('#EDEFF2', '#3C4654'),
    'link': ('#E8F0FE', '#3559C7'), 'note': ('#F7F7F7', '#8A9099'),
}
LANE = {'Presentation': '#2F6DB5', 'Application logic': '#6B4AA0', 'Integration': '#B5602F', 'Data': '#1F7A7A'}


def hexc(h):
    return colors.HexColor(h)


def stamp(canvas, title, author, subject=''):
    canvas.setTitle(title)
    canvas.setAuthor(author or '')
    canvas.setCreator(author or '')
    canvas.setProducer(author or '')
    canvas.setSubject(subject or title)
