from flask import Flask, request, redirect, flash, jsonify
import werkzeug

from reader.app import get_flashed_messages_by_prefix, redirect_to_referrer, is_safe_url


app = Flask(
    __name__,
    template_folder='reader/templates',
    static_folder='reader/static',
)
app.secret_key = 'secret'
app.template_global()(get_flashed_messages_by_prefix)


@app.route('/')
def root():
    return app.jinja_env.from_string("""

{% import "macros.html" as macros %}

<!doctype html>

<meta name="viewport" content="width=device-width" />
<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">

<script>

// TODO: handle bad status code
// TODO: handle parse errors
// TODO: handle timeouts
// TODO: handle ok/err
// TODO: autoregister buttons based on class or whatever


function do_json_request(data, callback) {
    var xhr = new XMLHttpRequest();

    xhr.onload = function () {
        callback(JSON.parse(xhr.response));
    }

    xhr.open('POST', {{ url_for('form') | tojson | safe }});
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('Content-Type', 'application/json');

    xhr.send(JSON.stringify(data));
}


function register_simple(button, callback) {
    button.onclick = function () {
        do_json_request({
            action: button.value,
        }, callback);
        return false;
    };
}

function register_confirm(collapsible, callback) {
    button = collapsible.querySelector('button[value=confirm]');

    while (collapsible.firstChild) {
        collapsible.removeChild(collapsible.firstChild);
    }
    collapsible.appendChild(button);

    var state = 'none';
    var original_text = button.innerHTML;
    var timeout_id = null;

    button.onclick = function () {
        if (state == 'none') {
            state = 'waiting';
            button.innerHTML = 'sure?';
            timeout_id = setTimeout(function () {
                state = 'none';
                button.innerHTML = original_text;
            }, 2000);
        }

        else if (state == 'waiting') {
            clearTimeout(timeout_id);
            timeout_id = null;
            do_json_request({
                action: button.value,
            }, callback);
            state = 'none';
            button.innerHTML = original_text;
        }

        else {
            alert('should not happen');
        }

        return false;
    };
}

function register_text(button, input, callback) {
    button.onclick = function () {
        do_json_request({
            action: button.value,
            text: input.value,
        }, callback);
        return false;
    };
}


window.onload = function () {

    function update_out(data) {
        document.querySelector('#out').innerHTML = JSON.stringify(data);
    }

    register_simple(
        document.querySelector('button[value=simple]'),
        update_out);
    register_confirm(
        document.querySelector('button[value=confirm]').parentElement.parentElement,
        update_out);
    register_text(
        document.querySelector('button[value=text]'),
        document.querySelector('input[name=text]'),
        update_out);

};


</script>


<form action="{{ url_for('form') }}" method="post">
<ul class="controls">

{{ macros.simple_button('simple', 'simple') }}
{{ macros.confirm_button('confirm', 'confirm') }}
{{ macros.text_input_button('text', 'text', 'text', 'text') }}

{% for message in get_flashed_messages_by_prefix(
    'simple',
    'confirm',
    'text',
) %}
<li class="error">{{ message }}
{% endfor %}

</ul>

<input type="hidden" name="next" value='{{ url_for('root', from='next') }}'>
<input type="hidden" name="next-simple" value='{{ url_for('root', from_action='next-simple') }}'>
<input type="hidden" name="next-confirm" value='{{ url_for('root', from_action='next-confirm') }}'>
<input type="hidden" name="next-text" value='{{ url_for('root', from_action='next-text') }}'>

</form>


{% for message in get_flashed_messages_by_prefix('message') %}
<pre>{{ message }}</pre>
{% endfor %}

<pre id='out'></pre>


""").render()


class APIThing:

    def __init__(self, blueprint, rule, endpoint):
        self.actions = {}
        self.really = {}
        blueprint.add_url_rule(rule, endpoint, methods=['POST'], view_func=self.dispatch)

    def dispatch_form(self):
        action = request.form['action']
        func = self.actions.get(action)
        if func is None:
            return "unknown action", 400
        next = request.form.get('next-' + action)
        if next is None:
            next = request.form['next']
        if not is_safe_url(next):
            return "bad next", 400
        if self.really[func]:
            really = request.form.get('really-' + action)
            if really is None:
                really = request.form.get('really')
            target = request.form.get('target')
            if really != 'really':
                category = (action, )
                if target is not None:
                    category += (target, )
                flash("{}: really not checked".format(action), category)
                return redirect_to_referrer()
        try:
            rv = func(request.form)
            flash(rv)
        except APIError as e:
            category = (action, )
            if e.category:
                category += e.category
            flash("{}: {}".format(action, e), category)
            return redirect_to_referrer()
        return redirect(next)

    def dispatch_json(self):
        data = werkzeug.MultiDict(request.get_json())
        action = data['action']
        func = self.actions.get(action)
        if func is None:
            return "unknown action", 400

        try:
            rv = func(data)
            rv = {'ok': rv}
        except APIError as e:
            category = (action, )
            if e.category:
                category += e.category
            rv = {'err': e.message}

        return jsonify(rv)

    def dispatch(self):
        if request.mimetype == 'application/x-www-form-urlencoded':
            return self.dispatch_form()
        if request.mimetype == 'application/json':
            return self.dispatch_json()
        return "bad content type", 400

    def __call__(self, func=None, *, really=False):

        def register(f):
            self.actions[f.__name__.replace('_', '-')] = f
            self.really[f] = really
            return f

        if func is None:
            return register
        return register(func)


class APIError(Exception):

    def __init__(self, message, category=None):
        super().__init__(message)
        self.message = message
        if category is not None:
            if not isinstance(category, tuple):
                category = (category, )
        self.category = category



form = APIThing(app, '/form', 'form')

@form
def simple(data):
    return 'simple'

@form(really=True)
def confirm(data):
    return 'confirm'

@form
def text(data):
    text = data['text']
    if text.startswith('err'):
        raise APIError(text, 'category')
    return 'text: %s' % text


