'''
    irctk.bot
    ---------
    
    This defines the main class, `Bot`, for use in creating new IRC bot apps.
'''

import os
import sys
import time
import inspect
import thread
import imp

from .config import Config
from .ircclient import TcpClient, IrcWrapper, IrcTestClient


class Context(object):
    def __init__(self, line, args):
        self.line = line
        self.args = args


class Bot(object):
    _instance = None
    root_path = os.path.abspath('')
    
    default_config = dict({
        'SERVER': 'irc.voxinfinitus.net',
        'PORT': 6697,
        'SSL': True,
        'TIMEOUT': 300,
        'NICK': 'Kaa',
        'REALNAME': 'Kaa the rock python',
        'CHANNELS': ['#voxinfinitus'],
        'PLUGINS': [],
        'EVENTS': []
        })
    
    def __init__(self):
        self.config = Config(self.root_path, self.default_config)
    
    def __new__(cls, *args, **kwargs):
        '''Here we override the `__new__` method in order to achieve a 
        singleton effect. In this way we can reload instances of the object 
        without having to worry about which instance we reference.'''
        
        if not cls._instance:
            cls._instance = super(Bot, cls).__new__(cls, *args, **kwargs)
        return cls._instance
    
    def _update_plugins(self, plugins, plugin):
        '''Updates a given list containing plugins, `plugins`, with a plugin 
        dictionary object, `plugin`.
        
        Usually used to update the PLUGINS or EVENTS list in the configuration 
        object.
        '''
        
        if not self.config.get(plugins):
            self.config[plugins] = []
        return self.config[plugins].append(plugin)
    
    def _send_reply(self, message, context, action=False, line_limit=400):
        '''TODO'''
        
        if context['sender'].startswith('#'):
            recipient = context['sender']
        else:
            recipient = context['user']
        
        messages = []
        def handle_long_message(message):
            message, extra = message[:line_limit], message[line_limit:]
            messages.append(message)
            if extra:
                handle_long_message(extra)
        handle_long_message(message)
        
        for message in messages:
            self.irc.send_message(recipient, message, action)
    
    def _dispatch_plugin(self, plugin, hook, context):
        '''TODO'''
        
        if context == hook or context.startswith(hook + ' '):
            plugin_args = plugin['context']['message'].split(hook, 1)[-1].strip()
            plugin_context = Context(plugin['context'], plugin_args)
            takes_args = inspect.getargspec(plugin['func']).args
            
            action = False
            if plugin.get('action') == True:
                action = True
            
            notice = False
            if plugin.get('notice') == True:
                notice = True
            
            if takes_args:
                message = plugin['func'](plugin_context)
            else:
                message = plugin['func']()
            
            if message:
                return self._send_reply(message, plugin_context.line, action)
    
    def _parse_input(self, prefix='.'):
        '''This internal method handles the parsing of commands and events.
        Hooks for commands are prefixed with a character, by default `.`. This 
        may be overriden by specifying `prefix`.
        
        A context is maintained by our IRC wrapper, `IrcWrapper`; referenced 
        as `self.irc`. In order to prevent a single line from being parsed 
        repeatedly a variable `stale` is set to either True or False. 
        
        If the context is fresh, i.e. not `stale`, we loop over the line 
        looking for matches to plugins.
        
        Once the context is consumed, we set the context variable `stale` to 
        True.
        '''
        
        while True:
            time.sleep(0.01)
            
            with self.irc.lock:
                context_stale = self.irc.context.get('stale')
                args = self.irc.context.get('args')
                command = self.irc.context.get('command')
                message = self.irc.context.get('message')
                while not context_stale and args:
                    if message.startswith(prefix):
                        for plugin in self.config['PLUGINS']:
                            plugin['context'] = self.irc.context # set context
                            hook = prefix + plugin['hook']
                            try:
                                thread.start_new_thread(self._dispatch_plugin, (plugin, hook, message))
                            except Exception, e:
                                self.logger.error(str(e))
                                continue
                    if command and command.isupper():
                        for event in self.config['EVENTS']:
                            event['context'] = self.irc.context
                            hook = event['hook']
                            try:
                                thread.start_new_thread(self._dispatch_plugin, (event, hook, command))
                            except Exception, e:
                                self.logger.error(str(e))
                                continue
                    
                    # we're done here, context is stale, give us fresh fruit!
                    context_stale = self.irc.context['stale'] = True
    
    def command(self, hook=None, **kwargs):
        '''This method provides a decorator that can be used to load a 
        function into the global plugins list.:
        
        If the `hook` parameter is provided the decorator will assign the hook 
        key to the value of `hook`, update the `plugin` dict, and then return 
        the wrapped function to the wrapper.
        
        Therein the plugin dictionary is updated with the `func` key whose 
        value is set to the wrapped function.
        
        Otherwise if no `hook` parameter is passed the, `hook` is assumed to 
        be the wrapped function and handled accordingly.
        '''
        
        plugin = {}
        
        def wrapper(f):
            plugin.setdefault('hook', f.func_name)
            plugin['func'] = f
            plugin['help'] = f.__doc__ if f.__doc__ else 'no help provided'
            self._update_plugins('PLUGINS', plugin)
            return f
        
        if kwargs or not inspect.isfunction(hook):
            if hook:
                plugin['hook'] = hook
            plugin.update(kwargs)
            return wrapper
        else:
            return wrapper(hook)
    
    def event(self, hook, **kwargs):
        '''This method provides a decorator that can be used to load a 
        function into the global events list.
        
        It assumes one parameter, `hook`, i.e. the event you wish to bind 
        this wrapped function to. For example, JOIN, which would call the 
        function on all JOIN events.
        '''
        
        plugin = {}
        
        def wrapper(f):
            plugin['func'] = f
            self._update_plugins('EVENTS', plugin)
            return f
        
        plugin['hook'] = hook
        plugin.update(kwargs)
        return wrapper
    
    def _reloader_loop(self, wait=1):
        '''This reloader is based off of the Flask reloader which in turn is 
        based off of the CherryPy reloader.
        
        This internal method takes on parameter, `wait`, the wait time given 
        in seconds. The default value is set to one second.
        '''
        
        def iter_module_files():
            for module in sys.modules.values():
                filename = getattr(module, '__file__', None)
                if filename:
                    old = None
                    while not os.path.isfile(filename):
                        old = filename
                        filename = os.path.dirname(filename)
                        if filename == old:
                            break
                    else:
                        if filename[-4:] in ('.pyc', '.pyo'):
                            filename = filename[:-1]
                        yield filename
        
        fnames = []
        fnames.extend(iter_module_files())
        self._reloader(fnames, wait=wait)
    
    def _reloader(self, fnames, wait=1):
        '''This reloader is based off of the Flask reloader which in turn is 
        based off of the CherryPy reloader.
        
        This internal method takes two paramters, `fnames` and `wait.` Here 
        we loop over a list of file names, `fnames`, using `os.stat` to 
        determine if the mtime of the file has been changed. If so we use 
        `imp.load_source` to reload the module.
        
        The `fnames` parameter should be a list of files names to be parsed by 
        the reloader.
        
        The `wait` parameter specifies the time in seconds to run 
        `time.sleep()`.
        ''' 
        
        mtimes = {}
        
        while True:
            for filename in fnames:
                try:
                    mtime = os.stat(filename).st_mtime
                except OSError:
                    continue
                
                old_time = mtimes.get(filename)
                if old_time is None:
                    mtimes[filename] = mtime
                elif mtime > old_time:
                    mtimes[filename] = mtime
                    
                    self.logger.info('Changes detected; reloading {0}'.format(filename))
                    
                    f = filename.split('/')[-1].split('.')[0]
                    try:
                        imp.load_source(f, filename)
                    except Exception, e:
                        self.logger.error('Failed loading plugin: ' + str(e))
                        continue
                    finally:
                        mtimes[filename] = mtime
                        
            time.sleep(wait)
    
    def run(self, wait=0.01):
        
        self.connection = TcpClient(
                self.config['SERVER'], 
                self.config['PORT'], 
                self.config['SSL'], 
                self.config['TIMEOUT']
                )
        
        self.irc = IrcWrapper(
                self.connection, 
                self.config['NICK'], 
                self.config['REALNAME'], 
                self.config['CHANNELS']
                )
        
        self.logger = self.connection.logger
        
        self.connection.connect()
        self.irc.run()
        
        thread.start_new_thread(self._parse_input, ())
        thread.start_new_thread(self._reloader_loop, ())
        
        while True:
            time.sleep(wait)


class TestBot(Bot):
    shutdown = False
    
    def __init__(self):
        self.config = Config(self.root_path, self.default_config)
        self.irc = IrcTestClient(
                self.config['NICK'], 
                self.config['REALNAME'], 
                self.config['CHANNELS']
                )
        self.connection = self.irc.connection
    
    def run(self):
        
        thread.start_new_thread(self._parse_input, ())
        
        while not self.shutdown:
            time.sleep(0.01)
