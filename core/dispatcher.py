'''
The bot will serve as the instance of `Irc()`. We should use bot as a means
for sending messages (otherwise we reinstantiate `Irc()` and commands or events
aren't associated with the proper instance).

To properly use `Dispatcher()` it will need to be imported into either a main.py
or bot.py where it will then use iterable instances of `Irc()` to send and 
receive events.

In this way we can acheive something along the lines of: `if hook in cmd_hooks: 
bot.cmd(cmd_hooks[hook](bot.event))`. This is the `_publish()` logic.

Because the dicts will live outside of classes, we should import the entire
namespace. Although we could put the `command()` and `subscribe()` functions
in a class it would seem unecessary.
'''

import inspect 
from collections import defaultdict

cmd_hooks = {} # store functions in a standard dictionary
sub_hooks = defaultdict(list) # store functions in a list associated with a hook

def command(hook=None):
    '''Associate a command hook with a function. For example `@command('google')`
       should call a given function with `google` hook, alternatively using 
       `@command` should use `func.func_name` as the hook. Uses cmd_hooks dict.
    '''

    def command_wrapper(func):
        if hook is None and func.func_name in cmd_hooks or hook in cmd_hooks:
            raise ValueError('Duplicate command hook found.')
        else:
            cmd_hooks[func.func_name] = func
        return func
        
    if inspect.isfunction(hook):
        return command_wrapper
    else:
        return command_wrapper(hook)

def subscribe(hook):
    '''Subscribe a function or functions to an event. For example 
       `@subscribe('JOIN')` should call a given function or functions with the 
       `JOIN` hook. Uses sub_hook dict.
    '''

    def subscribe_wrapper(func):
        sub_hooks[hook].append(func)
        return func
    
    return subscribe_wrapper

def dispatch(bot, event):
    for func in sub_hooks[event.hook]:
        func(bot, event.args)


#class Publisher(object): # Dispatcher
#    '''Publish functions associated with hooks to `Irc.cmd()`. Load 
#       subscriptions with `load()`.
#    '''
