from models import Fuente
from parsers.amex import AmexParser
from parsers.bbva import BBVAParser
from parsers.galicia import GaliciaParser
from parsers.mercadopago import MercadoPagoParser

PARSERS = {
    "amex":        AmexParser(),
    "bbva_mc":     BBVAParser(Fuente.BBVA_MC),
    "bbva_visa":   BBVAParser(Fuente.BBVA_VISA),
    "galicia_mc":  GaliciaParser(),
    "mercadopago": MercadoPagoParser(),
}
