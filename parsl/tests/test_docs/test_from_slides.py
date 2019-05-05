from parsl.app.app import App
from parsl.data_provider.files import File


@App('bash')
def echo(message, outputs=[]):
    return 'echo {0} &> {outputs[0]}'


@App('python')
def cat(inputs=[]):
    with open(inputs[0].filepath) as f:
        return f.readlines()


def test_slides():
    """Testing code snippet from slides """

    hello = echo("Hello World!", outputs=[File('hello1.txt')])
    message = cat(inputs=[File(hello.outputs[0].filepath)])

    # Waits. This need not be in the slides.
    print(hello.result())
    print(message.result())