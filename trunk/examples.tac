from twisted.application import internet, service
from nevow import appserver
from forms.examples import main

application = service.Application('examples')
service = internet.TCPServer(8000, main.makeSite(application))
service.setServiceParent(application)

