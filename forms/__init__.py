"""A package (for Nevow) for defining the schema, validation and rendering of
HTML forms.
"""

from nevow import static

from forms.types import *
from forms.validation import *
from forms.widget import *
from forms.form import Form, ResourceMixin, renderForm
from forms import iforms

def widgetFactory(widgetClass, *a, **k):
    def _(original):
        return widgetClass(original, *a, **k)
    return _
    
import os.path
defaultCSS = static.File(os.path.join(os.path.split(__file__)[0], 'forms.css'))

# Register standard adapters
from nevow.compy import registerAdapter
from forms import converters
registerAdapter(TextInput, String, iforms.IWidget)
registerAdapter(TextInput, Integer, iforms.IWidget)
registerAdapter(TextInput, Float, iforms.IWidget)
registerAdapter(Checkbox, Boolean, iforms.IWidget)
registerAdapter(DatePartsInput, Date, iforms.IWidget)
registerAdapter(TextInput, Time, iforms.IWidget)
registerAdapter(FileUpload, File, iforms.IWidget)
from forms import util
registerAdapter(util.SequenceKeyLabelAdapter, tuple, iforms.IKey)
registerAdapter(util.SequenceKeyLabelAdapter, tuple, iforms.ILabel)
registerAdapter(converters.NullConverter, String, iforms.IStringConvertible)
registerAdapter(converters.DateToDateTupleConverter, Date, iforms.IDateTupleConvertible)
registerAdapter(converters.BooleanToStringConverter, Boolean, iforms.IBooleanConvertible)
registerAdapter(converters.IntegerToStringConverter, Integer, iforms.IStringConvertible)
registerAdapter(converters.FloatToStringConverter, Float, iforms.IStringConvertible)
registerAdapter(converters.DateToStringConverter, Date, iforms.IStringConvertible)
registerAdapter(converters.TimeToStringConverter, Time, iforms.IStringConvertible)
registerAdapter(converters.NullConverter, File, iforms.IFileConvertible)
del registerAdapter

