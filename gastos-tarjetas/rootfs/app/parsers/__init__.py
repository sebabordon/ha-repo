from models import Fuente
from parsers.amex import AmexParser
from parsers.bbva import BBVAParser
from parsers.bbva_cuenta import BBVACuentaParser
from parsers.galicia import GaliciaParser
from parsers.mercadopago import MercadoPagoParser

PARSERS = {
    "amex":        AmexParser(),
    "bbva_mc":     BBVAParser(Fuente.BBVA_MC),
    "bbva_visa":   BBVAParser(Fuente.BBVA_VISA),
    "bbva_cuenta": BBVACuentaParser(),
    "galicia_mc":  GaliciaParser(),
    "mercadopago": MercadoPagoParser(),
}
