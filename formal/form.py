"""
Form implementation and high-level renderers.
"""

from zope.interface import Interface
from twisted.internet import defer
from twisted.python.components import registerAdapter
from nevow import appserver, context, loaders, inevow, rend, tags as T, url
from nevow.util import getPOSTCharset
from formal import iformal, util, validation
from resourcemanager import ResourceManager
from zope.interface import implements


SEPARATOR = '!!'
FORMS_KEY = '__nevow_form__'
WIDGET_RESOURCE_KEY = 'widget_resource'


def renderForm(name):

    def _(ctx, data):

        def _processForm( form, ctx, name ):
            # Remember the form
            ctx.remember(form, iformal.IForm)

            # Create a keyed tag that will render the form when flattened.
            tag = T.invisible(key=name)[inevow.IRenderer(form)]

            # Create a new context, referencing the above tag, so that we don't
            # pollute the current context with anything the form needs during
            # rendering.
            ctx = context.WovenContext(parent=ctx, tag=tag)

            # Find errors for *this* form and remember things on the context
            errors = iformal.IFormErrors(ctx, None)
            if errors is not None and errors.formName == name:
                ctx.remember(errors.data, iformal.IFormData)
            else:
                ctx.remember(None, iformal.IFormErrors)
                ctx.remember(form.data or {}, iformal.IFormData)

            return ctx

        d = defer.succeed( ctx )
        d.addCallback( locateForm, name )
        d.addCallback( _processForm, ctx, name )
        return d

    return _


class Action(object):
    """Tracks an action that has been added to a form.
    """
    def __init__(self, callback, name, validate, label):
        self.callback = callback
        self.name = name
        self.validate = validate
        if label is None:
            self.label = util.titleFromName(name)
        else:
            self.label = label



class Field(object):


    itemParent = None


    def __init__(self, name, type, widgetFactory=None, label=None,
            description=None, cssClass=None):
        if not util.validIdentifier(name):
            raise ValueError('%r is an invalid field name'%name)
        if label is None:
            label = util.titleFromName(name)
        if widgetFactory is None:
            widgetFactory = iformal.IWidget
        self.name = name
        self.type = type
        self.widgetFactory = widgetFactory
        self.label = label
        self.description = description
        self.cssClass = cssClass


    def setItemParent(self, itemParent):
        self.itemParent = itemParent


    def _getKey(self):
        parts = [self.name]
        parent = self.itemParent
        while parent is not None:
            parts.append(parent.name)
            parent = parent.itemParent
        parts.reverse()
        return '.'.join(parts)


    key = property(_getKey)


    def makeWidget(self):
        return self.widgetFactory(self.type)


    def process(self, ctx, form, args, errors):

        # If the type is immutable then copy the original value to args in case
        # another validation error causes this field to be re-rendered.
        if self.type.immutable:
            args[self.key] = form.data.get(self.key)
            return

        # Process the input using the widget, storing the data back on the form.
        try:
            form.data[self.key] = self.makeWidget().processInput(ctx, self.key, args)
        except validation.FieldError, e:
            if e.fieldName is None:
                e.fieldName = self.key
            errors.add(e)



class FieldFragment(rend.Fragment):
    implements(inevow.IRenderer)


    docFactory = loaders.stan(
        T.div(id=T.slot('fieldId'), _class=T.slot('class'),
                render=T.directive('field'))[
            T.label(_class='label', _for=T.slot('id'))[T.slot('label')],
            T.div(_class='inputs')[T.slot('inputs')],
            T.slot('description'),
            T.slot('message'),
            ])


    hiddenDocFactory = loaders.stan(
            T.invisible(render=T.directive('field'))[T.slot('inputs')])


    def __init__(self, field):
        self.field = field
        # Nasty hack to work out if this is a hidden field. Keep the widget
        # for later anyway.
        self.widget = field.makeWidget()
        if getattr(self.widget, 'inputType', None) == 'hidden':
            self.docFactory = self.hiddenDocFactory


    def render_field(self, ctx, data):

        # The field we're rendering
        field = self.field

        # Get stuff from the context
        formData = iformal.IFormData(ctx)
        formErrors = iformal.IFormErrors(ctx, None)

        # Find any error
        if formErrors is None:
            error = None
        else:
            error = formErrors.getFieldError(field.name)

        # Build the error message
        if error is None:
            message = ''
        else:
            message = T.div(class_='message')[error.message]

        # Create the widget (it's created in __init__ as a hack)
        widget = self.widget

        # Build the list of CSS classes
        classes = [
            'field',
            field.type.__class__.__name__.lower(),
            widget.__class__.__name__.lower(),
            ]
        if field.type.required:
            classes.append('required')
        if field.cssClass:
            classes.append(cssClass)
        if error:
            classes.append('error')

        # Create the widget and decide the method that should be called
        if field.type.immutable:
            render = widget.renderImmutable
        else:
            render = widget.render

        # Fill the slots
        ctx.tag.fillSlots('id', util.render_cssid(field.key))
        ctx.tag.fillSlots('fieldId', [util.render_cssid(field.key), '-field'])
        ctx.tag.fillSlots('class', ' '.join(classes))
        ctx.tag.fillSlots('label', field.label)
        ctx.tag.fillSlots('inputs', render(ctx, field.key, formData,
            formErrors))
        ctx.tag.fillSlots('message', message)
        ctx.tag.fillSlots('description',
                T.div(class_='description')[field.description or ''])

        return ctx.tag



registerAdapter(FieldFragment, Field, inevow.IRenderer)



class Group(object):


    itemParent = None


    def __init__(self, name, label=None, description=None):
        if label is None:
            label = util.titleFromName(name)
        self.name = name
        self.label = label
        self.description = description
        self.items = []


    def setItemParent(self, itemParent):
        self.itemParent = itemParent


    def add(self, item):
        self.items.append(item)
        item.setItemParent(self)



class GroupFragment(rend.Fragment):


    docFactory = loaders.stan(
            T.fieldset(id=T.slot('id'), render=T.directive('group'))[
                T.legend[T.slot('label')],
                T.div(class_='description')[T.slot('description')],
                T.slot('items'),
                ]
            )


    def __init__(self, group):
        super(GroupFragment, self).__init__()
        self.group = group


    def render_group(self, ctx, data):
        group = self.group
        ctx.tag.fillSlots('id', util.render_cssid(group.name))
        ctx.tag.fillSlots('label', group.label)
        ctx.tag.fillSlots('description', group.description or '')
        ctx.tag.fillSlots('items', [inevow.IRenderer(item) for item in
                group.items])
        return ctx.tag



registerAdapter(GroupFragment, Group, inevow.IRenderer)



class Form(object):

    implements( iformal.IForm )

    callback = None
    actions = None

    def __init__(self, callback=None):
        if callback is not None:
            self.callback = callback
        self.resourceManager = ResourceManager()
        self.data = {}
        self.items = []

    def add(self, item):
        self.items.append(item)

    def addField(self, name, type, widgetFactory=None, label=None,
            description=None, cssClass=None):
        self.add(Field(name, type, widgetFactory, label, description, cssClass))

    def getItemByName(self, name):
        for item in self.items:
            if item.name == name:
                return item
        raise KeyError("No item called %r" % name)

    def addAction(self, callback, name="submit", validate=True, label=None):
        if self.actions is None:
            self.actions = []
        if name in [action.name for action in self.actions]:
            raise ValueError('Action with name %r already exists.' % name)
        self.actions.append( Action(callback, name, validate, label) )

    def process(self, ctx):

        # Get the request args
        requestArgs = inevow.IRequest(ctx).args

        # Decode the request arg names
        charset = getPOSTCharset(ctx)
        args = dict([(k.decode(charset),v) for k,v in requestArgs.iteritems()])

        # Find the callback to use, defaulting to the form default
        callback, validate = self.callback, True
        if self.actions is not None:
            for action in self.actions:
                if action.name in args:
                    # Remove it from the data
                    args.pop(action.name)
                    # Remember the callback and whether to validate
                    callback, validate = action.callback, action.validate
                    break

        if callback is None:
            raise Exception('The form has no callback and no action was found.')

        # Store an errors object in the context
        errors = FormErrors(self.name)
        errors.data = args
        ctx.remember(errors, iformal.IFormErrors)

        # Iterate the items and collect the form data and/or errors.
        for item in self.items:
            item.process(ctx, self, args, errors)

        if errors and validate:
            return errors

        def _clearUpResources( r ):
            if not errors:
                self.resourceManager.clearUpResources()
            return r

        d = defer.maybeDeferred(callback, ctx, self, self.data)
        d.addCallback( _clearUpResources )
        d.addErrback(self._cbFormProcessingFailed, ctx)
        return d

    def _cbFormProcessingFailed(self, failure, ctx):
        e = failure.value
        failure.trap(validation.FormError, validation.FieldError)
        errors = iformal.IFormErrors(ctx)
        errors.add(failure.value)
        return errors


class FormErrors(object):
    implements( iformal.IFormErrors )

    def __init__(self, formName):
        self.formName = formName
        self.errors = []

    def add(self, error):
        self.errors.append(error)

    def getFieldError(self, name):
        fieldErrors = [e for e in self.errors if isinstance(e, validation.FieldError)]
        for error in fieldErrors:
            if error.fieldName == name:
                return error

    def getFormErrors(self):
        return self.errors

    def __nonzero__(self):
        return len(self.errors) != 0


class FormResource(object):
    implements(inevow.IResource)

    def locateChild(self, ctx, segments):
        # The form name is the first segment
        formName = segments[0]
        if segments[1] == WIDGET_RESOURCE_KEY:
            # Serve up file from the resource manager
            d = locateForm(ctx, formName)
            d.addCallback(self._fileFromWidget, ctx, segments[2:])
            return d
        return appserver.NotFound

    def renderHTTP(self, ctx):
        raise NotImplemented()

    def _fileFromWidget(self, form, ctx, segments):
        ctx.remember(form, iformal.IForm)
        widget = form.getItemByName(segments[0]).makeWidget()
        return widget.getResource(ctx, segments[0], segments[1:])


class FormsResourceBehaviour(object):
    """
    I provide the IResource behaviour needed to process and render a page
    containing a Form.
    """

    def __init__(self, **k):
        parent = k.pop('parent')
        super(FormsResourceBehaviour, self).__init__(**k)
        self.parent = parent

    def locateChild(self, ctx, segments):
        if segments[0] == FORMS_KEY:
            self.remember(ctx)
            return FormResource(), segments[1:]
        return appserver.NotFound

    def renderHTTP(self, ctx):
        # Get hold of the request
        request = inevow.IRequest(ctx)
        # Intercept POST requests to see if it's for me
        if request.method != 'POST':
            return None
        # Try to find the form name
        formName = request.args.get(FORMS_KEY, [None])[0]
        if formName is None:
            return None
        # Find the actual form and process it
        self.remember(ctx)
        d = defer.succeed(ctx)
        d.addCallback(locateForm, formName)
        d.addCallback(self._processForm, ctx)
        return d

    def remember(self, ctx):
        ctx.remember(self.parent, iformal.IFormFactory)

    def render_form(self, name):
        def _(ctx, data):
            self.remember(ctx)
            return renderForm(name)
        return _

    def _processForm(self, form, ctx):
        ctx.remember(form, iformal.IForm)
        d = defer.maybeDeferred(form.process, ctx)
        d.addCallback(self._formProcessed, ctx)
        return d

    def _formProcessed(self, result, ctx):
        if isinstance(result, FormErrors):
            return None
        elif result is None:
            resource = url.URL.fromContext(ctx)
        else:
            resource = result
        return resource


class ResourceMixin(object):
    implements( iformal.IFormFactory )
    
    __formsBehaviour = None
    
    def __behaviour(self):
        if self.__formsBehaviour is None:
            self.__formsBehaviour = FormsResourceBehaviour(parent=self)
        return self.__formsBehaviour
    
    def locateChild(self, ctx, segments):
        def gotResult(result):
            if result is not appserver.NotFound:
                return result
            return super(ResourceMixin, self).locateChild(ctx, segments)
        self.remember(self, iformal.IFormFactory)
        d = defer.maybeDeferred(self.__behaviour().locateChild, ctx, segments)
        d.addCallback(gotResult)
        return d

    def renderHTTP(self, ctx):
        def gotResult(result):
            if result is not None:
                return result
            return super(ResourceMixin, self).renderHTTP(ctx)
        self.remember(self, iformal.IFormFactory)
        d = defer.maybeDeferred(self.__behaviour().renderHTTP, ctx)
        d.addCallback(gotResult)
        return d

    def render_form(self, name):
        return self.__behaviour().render_form(name)

    def formFactory(self, ctx, name):
        factory = getattr(self, 'form_%s'%name, None)
        if factory is not None:
            return factory(ctx)
        s = super(ResourceMixin, self)
        if hasattr(s,'formFactory'):
            return s.formFactory(ctx, name)


class IKnownForms(Interface):
    """Marker interface used to locate a dict instance containing the named
    forms we know about during this request.
    """


class KnownForms(dict):
    implements( IKnownForms )


def locateForm(ctx, name):
    """Locate a form by name.

    Initially, a form is located by calling on an IFormFactory that is found
    on the context. Once a form has been found, it is remembered in an
    KnownForms instance for the lifetime of the request.

    This ensures that the form that is located during form processing will be
    the same instance that is located when a form is rendered after validation
    failure.
    """
    # Get hold of the request
    request = inevow.IRequest(ctx)
    # Find or create the known forms instance
    knownForms = request.getComponent(IKnownForms)
    if knownForms is None:
        knownForms = KnownForms()
        request.setComponent(IKnownForms, knownForms)
    # See if the form is already known
    form = knownForms.get(name)
    if form is not None:
        return form
    # Not known yet, ask a form factory to create the form
    factory = ctx.locate(iformal.IFormFactory)

    def cacheForm( form, name ):
        if form is None:
            raise Exception('Form %r not found'%name)
        form.name = name
        # Make it a known
        knownForms[name] = form
        return form

    d = defer.succeed( None )
    d.addCallback( lambda r : factory.formFactory( ctx, name ) )
    d.addCallback( cacheForm, name )
    return d

def widgetResourceURL(name):
    return url.here.child(FORMS_KEY).child(name).child(WIDGET_RESOURCE_KEY)

def widgetResourceURLFromContext(ctx,name):
    # Could this replace widgetResourceURL?
    u = url.URL.fromContext(ctx)
    if u.pathList()[-1] != FORMS_KEY:
        u = u.child(FORMS_KEY)
    return u.child(name).child(WIDGET_RESOURCE_KEY)

class FormRenderer(object):
    implements( inevow.IRenderer )

    loader = loaders.stan(
            T.form(**{'id': T.slot('formId'), 'action': T.slot('formAction'),
                'class': 'nevow-form', 'method': 'post', 'enctype':
                'multipart/form-data', 'accept-charset': 'utf-8'})[
            T.div[
                T.input(type='hidden', name='_charset_'),
                T.input(type='hidden', name=FORMS_KEY, value=T.slot('formName')),
                T.slot('formErrors'),
                T.slot('formItems'),
                T.div(class_='actions')[
                    T.slot('formActions'),
                    ],
                ],
            ]
        )

    def __init__(self, original, *a, **k):
        super(FormRenderer, self).__init__(*a, **k)
        self.original = original

    def rend(self, ctx, data):
        tag = T.invisible[self.loader.load()]
        tag.fillSlots('formName', self.original.name)
        tag.fillSlots('formId', util.keytocssid(ctx.key))
        tag.fillSlots('formAction', url.here)
        tag.fillSlots('formErrors', self._renderErrors)
        tag.fillSlots('formItems', self._renderItems)
        tag.fillSlots('formActions', self._renderActions)
        return tag

    def _renderErrors(self, ctx, data):
        errors = iformal.IFormErrors(ctx, None)
        if errors is not None:
            errors = errors.getFormErrors()
        if not errors:
            return ''

        errorList = T.ul()
        for error in errors:
            if isinstance(error, validation.FormError):
                errorList[ T.li[ error.message ] ]
        for error in errors:
            if isinstance(error, validation.FieldError):
                item = self.original.getItemByName(error.fieldName)
                errorList[ T.li[ T.strong[ item.label, ' : ' ], error.message ] ]
        return T.div(class_='errors')[ T.p['Please correct the following errors:'], errorList ]

    def _renderItems(self, ctx, data):
        if self.original.items is None:
            yield ''
            return
        for item in self.original.items:
            yield inevow.IRenderer(item)

    def _renderActions(self, ctx, data):

        if self.original.actions is None:
            yield ''
            return

        for action in self.original.actions:
            yield T.invisible(data=action, render=self._renderAction)

    def _renderAction(self, ctx, data):
        return T.input(type='submit', id='%s-action-%s'%(util.keytocssid(ctx.key), data.name), name=data.name, value=data.label)


registerAdapter(FormRenderer, Form, inevow.IRenderer)

