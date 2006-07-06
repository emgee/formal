import pkg_resources
from twisted.python import reflect
from nevow import appserver, loaders, rend, static, tags as T, url
import forms

DOCTYPE = T.xml('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">')
CHARSET = T.xml('<meta http-equiv="content-type" content="text/html; charset=utf-8" />')

examples = [
    'forms.examples.simple',
    'forms.examples.types',
    'forms.examples.required',
    'forms.examples.missing',
    'forms.examples.prepopulate',
    'forms.examples.fileupload',
    'forms.examples.smartupload',
    'forms.examples.selections',
    'forms.examples.dates',
    'forms.examples.actionbuttons',
    ]

def makeSite(application):
    root = RootPage()
    site = appserver.NevowSite(root, logPath='web.log')
    return site

class RootPage(rend.Page):

    docFactory = loaders.stan(
        T.invisible[
            DOCTYPE,
            T.html[
                T.head[
                    CHARSET,
                    T.title['Forms Examples'],
                    T.link(rel='stylesheet', type='text/css', href=url.root.child('examples.css')),
                    ],
                T.body[
                    T.directive('examples'),
                    ],
                ],
            ],
        )

    def render_examples(self, ctx, data):
        for name in examples:
            module = reflect.namedAny(name)
            yield T.div(class_='example')[
                T.h1[T.a(href=url.here.child(name))[module.title]],
                T.p[module.description],
                ]

    def childFactory(self, ctx, name):
        if name in examples:
            return FormExamplePage(reflect.namedAny(name))



class FormExamplePage(forms.ResourceMixin, rend.Page):
    docFactory = loaders.stan(
        T.invisible[
            DOCTYPE,
            T.html[
                T.head[
                    CHARSET,
                    T.title(data=T.directive('title'), render=rend.data),
                    T.link(rel='stylesheet', type='text/css', href=url.root.child('examples.css')),
                    T.link(rel='stylesheet', type='text/css', href=url.root.child('forms.css')),
                    ],
                T.body[
                    T.h1(data=T.directive('title'), render=rend.data),
                    T.p(data=T.directive('description'), render=rend.data),
                    T.directive('form example'),
                    ],
                ],
            ],
        )

    def data_title(self, ctx, data):
        return self.original.title

    def data_description(self, ctx, data):
        return self.original.description

    def form_example(self, ctx):
        return self.original.makeForm(ctx)


# Add child_ attributes
examples_css = pkg_resources.resource_filename('forms.examples', 'examples.css')
setattr(RootPage, 'child_examples.css', static.File(examples_css))
setattr(RootPage, 'child_forms.css', forms.defaultCSS)
