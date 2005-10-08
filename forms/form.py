"""
Form implementation and high-level renderers.
"""

from twisted.internet import defer
from nevow import context, loaders, inevow, tags as T, url
from nevow.compy import registerAdapter, Interface
from forms import iforms, util, validation
from resourcemanager import ResourceManager
from zope.interface import implements


ACTION_SEP = '!!'
FORM_ACTION = '__nevow_form__'
WIDGET_RESOURCE = '__widget_res__'


def renderForm(name):

    def _(ctx, data):

        def _processForm( form, ctx, name ):
            # Find the form
            ctx.remember(form, iforms.IForm)

            # Create a keyed tag that will render the form when flattened.
            tag = T.invisible(key=name)[inevow.IRenderer(form)]

            # Create a new context, referencing the above tag, so that we don't
            # pollute the current context with anything the form needs during
            # rendering.
            ctx = context.WovenContext(parent=ctx, tag=tag)

            # Find errors for *this* form and remember things on the context
            errors = iforms.IFormErrors(ctx, None)
            if errors is not None and errors.formName == name:
                ctx.remember(errors.data, iforms.IFormData)
            else:
                ctx.remember(None, iforms.IFormErrors)
                ctx.remember(form.data or {}, iforms.IFormData)

            return ctx

        d = defer.succeed( ctx )
        d.addCallback( locateForm, name )
        d.addCallback( _processForm, ctx, name )
        return d

    return _


class Action(object):
    """Tracks an action that has been added to a form.
    """
    def __init__(self, callback, name, validate):
        self.callback = callback
        self.name = name
        self.validate = validate


class Form(object):

    implements( iforms.IForm )

    callback = None
    items = None
    actions = None
    widgets = None
    data = None

    def __init__(self, callback=None):
        if callback is not None:
            self.callback = callback
        self.resourceManager = ResourceManager()

    def addField(self, name, type, widgetFactory=None, label=None, description=None, cssClass=None):
        if self.items is None:
            self.items = []
        type.name = name
        if label is None:
            label = util.titleFromName(name)
        self.items.append( (name,type,label,description,cssClass) )
        if widgetFactory is not None:
            if self.widgets is None:
                self.widgets = {}
            self.widgets[name] = widgetFactory

    def addAction(self, callback, name="submit", validate=True):
        if self.actions is None:
            self.actions = []
        if name in [action.name for action in self.actions]:
            raise ValueError('Action with name %r already exists.' % name)
        self.actions.append( Action(callback, name, validate) )

    def widgetForItem(self, itemName):

        for name, type, label, description, cssClass in self.items:
            if name == itemName:
                break
        else:
            raise KeyError()

        if self.widgets is not None:
            try:
                widgetFactory = self.widgets[name]
            except KeyError:
                pass
            else:
                return widgetFactory(type)

        return iforms.IWidget(type)

    def process(self, ctx):

        # Unflatten the request into nested dicts.
        args = {}
        for name, value in inevow.IRequest(ctx).args.iteritems():
            name = name.split('.')
            group, name = name[:-1], name[-1]
            d = args
            for g in group:
                d = args.setdefault(g,{})
            d[name] = value

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
        ctx.remember(errors, iforms.IFormErrors)

        # Iterate the items and collect the form data and/or errors.
        data = {}
        for name, type, label, description, cssClass in self.items:
            try:
                if not type.immutable:
                    data[name] = self.widgetForItem(name).processInput(ctx, name, args)
                else:
                    data[name] = self.data.get(name)
                    errors.data[name] = self.data.get(name)
            except validation.FieldError, e:
                if validate:
                    if e.fieldName is None:
                        e.fieldName = name
                    errors.add(e)

        if errors:
            return errors

        # toType
        for name, type, label, description, cssClass in self.items:
            widget = self.widgetForItem(name)
            if hasattr( widget, 'convertibleFactory' ) and not type.immutable:
                data[name] = widget.convertibleFactory(type).toType( data.get(name) )

        def _clearUpResources( r ):
            self.resourceManager.clearUpResources()
            return r

        d = defer.maybeDeferred(callback, ctx, self, data)
        d.addCallback( _clearUpResources )
        d.addErrback(self._cbFormProcessingFailed, ctx)
        return d

    def _cbFormProcessingFailed(self, failure, ctx):
        e = failure.value
        failure.trap(validation.FormError, validation.FieldError)
        errors = iforms.IFormErrors(ctx)
        errors.add(failure.value)
        return errors


class FormErrors(object):
    implements( iforms.IFormErrors )

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
        return [e for e in self.errors if isinstance(e, validation.FormError)]

    def __nonzero__(self):
        return len(self.errors) != 0


class ResourceMixin(object):
    implements( iforms.IFormFactory )

    def __init__(self, *a, **k):
        super(ResourceMixin, self).__init__(*a, **k)
        self.remember(self, iforms.IFormFactory)

    def render_form(self, name):
        def _(ctx, data):
            return renderForm(name)
        return _

    def formFactory(self, ctx, name):

        factory = getattr(self, 'form_%s'%name, None)
        if factory is not None:
            return factory(ctx)

        s = super(ResourceMixin, self)
        if hasattr(s,'formFactory'):
            return s.formFactory(ctx, name)

    def locateChild(self, ctx, segments):

        # Leave now if this it not meant for me.
        if not segments[0].startswith(FORM_ACTION) and not segments[0].startswith(WIDGET_RESOURCE):
            return super(ResourceMixin, self).locateChild(ctx, segments)

        # Find the form name, the form and remember them.
        formName = segments[0].split(ACTION_SEP)[1]
        d = defer.succeed( ctx )
        d.addCallback( locateForm, formName )
        d.addCallback( self._processForm, ctx, segments )
        return d

    def _processForm( self, form, ctx, segments ):
        ctx.remember(form, iforms.IForm)

        # Serve up file from the resource manager
        if segments[0].startswith( WIDGET_RESOURCE ):
            return self._fileFromWidget( ctx, form, segments[1:] )

        # Process the form.
        d = defer.maybeDeferred(form.process, ctx)
        d.addCallback(self._formProcessed, ctx)
        return d


    def _fileFromWidget( self, ctx, form, segments ):
        widget = form.widgetForItem( segments[0] )
        return widget.getResource( ctx, segments[1:] )

    def _formProcessed(self, r, ctx):
        if isinstance(r, FormErrors):
            if r:
                return NoAddSlashHack(self), ()
            else:
                r = None
        if r is None:
            r = url.URL.fromContext(ctx)
        return r, ()


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
    factory = iforms.IFormFactory(ctx)

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

def formAction(name):
    return '%s%s%s' % (FORM_ACTION, ACTION_SEP, name)

def formWidgetResource(name):
    return '%s%s%s' % (WIDGET_RESOURCE, ACTION_SEP, name)


class FormRenderer(object):
    implements( inevow.IRenderer )

    loader = loaders.stan(
        T.form(id=T.slot('id'), action=T.slot('action'), class_='nevow-form', method='post', enctype='multipart/form-data', **{'accept-charset':'utf-8'})[
            T.fieldset[
                T.input(type='hidden', name='_charset_'),
                T.slot('errors'),
                T.slot('items'),
                T.div(id=T.slot('fieldId'), pattern='item', _class=T.slot('class'))[
                    T.label(_class='label', _for=T.slot('id'))[T.slot('label')],
                    T.div(_class='inputs')[T.slot('inputs')],
                    T.slot('description'),
                    T.slot('message'),
                    ],
                T.div(class_='hiddenitems')[
                    T.slot('hiddenitems'),
                    T.invisible(pattern="hiddenitem")[T.slot('inputs')]
                    ],
                T.div(class_='actions')[
                    T.slot('actions'),
                    ],
                ],
            ]
        )

    def __init__(self, original, *a, **k):
        super(FormRenderer, self).__init__(*a, **k)
        self.original = original

    def rend(self, ctx, data):

        segs = inevow.ICurrentSegments(ctx)
        if segs and segs[-1].startswith(FORM_ACTION):
            urlFactory = url.here.sibling
        else:
            urlFactory = url.here.child

        tag = T.invisible[self.loader.load()]
        tag.fillSlots('id', util.keytocssid(ctx.key))
        tag.fillSlots('action', urlFactory(formAction(self.original.name)))
        tag.fillSlots('errors', self._renderErrors)
        tag.fillSlots('items', self._renderItems)
        tag.fillSlots('hiddenitems', self._renderHiddenItems)
        tag.fillSlots('actions', self._renderActions)
        return tag

    def _renderErrors(self, ctx, data):
        errors = iforms.IFormErrors(ctx, None)
        if errors is not None:
            errors = errors.getFormErrors()
        if not errors:
            return ''
        return T.div(class_='errors')[
            T.p['Please correct the following errors:'],
            T.ul[[T.li[str(error)] for error in errors]],
            ]

    def _renderItems(self, ctx, data):
        if self.original.items is None:
            yield ''
            return
        itemPattern = inevow.IQ(ctx).patternGenerator('item')
        for item in self.original.items:
            widget = self.original.widgetForItem(item[0])
            if getattr(widget,'inputType','') != 'hidden':
                yield itemPattern(key=item[0], data=item, render=self._renderItem)

    def _renderHiddenItems(self, ctx, data):
        if self.original.items is None:
            yield ''
            return
        hiddenItemPattern = inevow.IQ(ctx).patternGenerator('hiddenitem')
        for item in self.original.items:
            widget = self.original.widgetForItem(item[0])
            if getattr(widget,'inputType','') == 'hidden':
                yield hiddenItemPattern(key=item[0], data=item, render=self._renderHiddenItem)

    def _renderItem(self, ctx, data):

        def _(ctx, data):

            name, type, label, description, cssClass = data
            form = self.original
            formErrors = iforms.IFormErrors(ctx, None)
            formData = iforms.IFormData(ctx)

            widget = form.widgetForItem(name)
            if formErrors is None:
                error = None
            else:
                error = formErrors.getFieldError(name)

            # Basic classes are 'field', the type's class name and the widget's
            # class name.
            classes = [
                'field',
                type.__class__.__name__.lower(),
                widget.__class__.__name__.lower(),
                ]
            # Add a required class
            if type.required:
                classes.append('required')
            # Add a user-specified class
            if cssClass:
                classes.append(cssClass)

            if error is None:
                message = ''
            else:
                classes.append('error')
                message = T.div(class_='message')[str(error)]

            ctx.tag.fillSlots('class', ' '.join(classes))
            ctx.tag.fillSlots('fieldId', '%s-field'%util.keytocssid(ctx.key))
            ctx.tag.fillSlots('id', util.keytocssid(ctx.key))
            ctx.tag.fillSlots('label', label)
            if type.immutable:
                render = widget.renderImmutable
            else:
                render = widget.render
            ctx.tag.fillSlots('inputs', render(ctx, name, formData, formErrors))
            ctx.tag.fillSlots('message', message)
            ctx.tag.fillSlots('description', T.div(class_='description')[description or ''])

            return ctx.tag

        return _

    def _renderHiddenItem(self, ctx, data):

        def _(ctx, data):

            name, type, label, description, cssClass = data
            form = self.original
            formErrors = iforms.IFormErrors(ctx, None)
            formData = iforms.IFormData(ctx)

            widget = form.widgetForItem(name)

            ctx.tag.fillSlots('fieldId', '%s-field'%util.keytocssid(ctx.key))
            ctx.tag.fillSlots('id', util.keytocssid(ctx.key))
            ctx.tag.fillSlots('inputs', widget.render(ctx, name, formData, formErrors))
            return ctx.tag

        return _

    def _renderActions(self, ctx, data):

        if self.original.actions is None:
            yield ''
            return

        for action in self.original.actions:
            yield T.invisible(data=action, render=self._renderAction)

    def _renderAction(self, ctx, data):
        return T.input(type='submit', id='%s-action-%s'%(util.keytocssid(ctx.key), data.name), name=data.name, value=util.titleFromName(data.name))


class NoAddSlashHack:
    implements( inevow.IResource )

    def __init__(self, wrapped):
        self.wrapped = wrapped

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    def renderHTTP(self, ctx):
        MISSING = object()
        addSlash = getattr(self.wrapped, 'addSlash', MISSING)
        if addSlash:
            self.wrapped.addSlash = False
        try:
            r = self.wrapped.renderHTTP(ctx)
        finally:
            if addSlash is not MISSING:
                self.wrapped.addSlash = addSlash
            else:
                del self.wrapped.addSlash
        return r


registerAdapter(FormRenderer, Form, inevow.IRenderer)

