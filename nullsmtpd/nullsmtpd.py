#!/usr/bin/env python3
"""
NullSMTPD module that allows to run a mock email server that just logs all incoming emails to a file
instead of actually trying to send them. Helps for developing applications that utilize email,
without spamming customers' emails and not having overhead from some GUI program.
"""
import argparse
import asyncio
import os
import time
import email
import sys

from aiosmtpd.controller import Controller
from aiosmtpd.handlers import Debugging
from aiosmtpd.smtp import SMTP as Server

from .logger import configure_logging
from .version import __version__

NULLSMTPD_DIRECTORY = os.path.join(os.path.expanduser("~"), ".nullsmtpd")

class MySMTPServer(Server):
    async def ehlo_hook(self):
        sys.stdout.write("EHLO HOOK" + '\n')
        return '250 HELP'

class MyController(Controller):
    def factory(self):
        #return MySMTPServer(self.handler)
        return Server(self.handler, data_size_limit=33554432, enable_SMTPUTF8=False, decode_data=False, hostname="10.10.10.248", ident=None, tls_context=None, require_starttls=False, timeout=300)

# pylint: disable=too-few-public-methods
class NullSMTPDHandler:
    """
    Handler for aiosmtpd module. This handler upon receiving a message will write the message
    to a file (as well as potentially logging the message if output_messages is True) instead
    of actually trying to send them anywhere. Useful for development of local systems being
    built in Vagrant/Docker and that we don't have a proper domain for and we don't really
    care to real all emails via a web interface.
    """
    def __init__(self, logger, mail_dir, output_messages=True):
        """

        :param logger: Logger to use for the handler
        :param mail_dir: Directory to write emails to
        :param output_messages: Boolean flag on whether to output messages to the logger
        """
        self.logger = logger
        if mail_dir is None or not isinstance(mail_dir, str):
            msg = "Invalid mail_dir variable: {}".format(mail_dir)
            self.logger.error(msg)
            raise SystemExit(msg)
        if not os.path.isdir(mail_dir):
            try:
                os.mkdir(mail_dir)
            except IOError as io_error:
                self.logger.error(str(io_error))
                raise
        self.mail_dir = mail_dir
        self.print_messages = output_messages is True
        self.logger.info("Mail Directory: {:s}".format(mail_dir))

    async def handle_HELO(self, server, session, envelope, hostname):
        
        self.logger.info('HELO from {:s}'.format(hostname))

        session.host_name = hostname

        return '250 {:s} Hello {:s}'.format("10.10.10.248", hostname)
    
    async def handle_EHLO(self, server, session, envelope, hostname):
        
        self.logger.info('EHLO from {:s}'.format(hostname))

        session.host_name = hostname

        return """\
250-PIPELINING
250-CHUNKING
250-STARTTLS
250 HELP"""

    async def handle_MAIL(self, server, session, envelope, address, mail_options):
        
        self.logger.info('MAIL FROM')

        envelope.mail_from = address

        return "250 OK"



    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):

        self.logger.info('RCPT')
        envelope.rcpt_tos.append(address)
        return "250 OK"

    # pylint: disable=invalid-name
    async def handle_DATA(self, _, __, envelope):
        """
        Process incoming email messages as they're received by the server. We take all messages
        and log them to a file in the directory (mailbox) pertaining to the recipient and then
        we save the file with {seconds from epoch}.{mailfrom}.msg so that the messages
        are self-organizing.

        :param _: server
        :param __: session
        :param envelope: Object containing details about the email (from, receiptents, messag)
        :return: string status code of server
        """
        # peer = session.peer
        #mail_from = envelope.mail_from
        #rcpt_tos = envelope.rcpt_tos
        #data = envelope.content.decode('utf-8')
        data = email.message_from_string(str(envelope.content,'utf-8'))
        """ 
        replace this part with downloading of attachment instead

        self.logger.info("Incoming mail from {:s}".format(mail_from))
        for recipient in rcpt_tos:
            self.logger.info("Mail received for {:s}".format(recipient))
            mail_file = "{:d}.{:s}.msg".format(int(time.time()), mail_from)
            mail_path = os.path.join(self.mail_dir, recipient, mail_file)
            if not os.path.isdir(os.path.join(self.mail_dir, recipient)):
                os.mkdir(os.path.join(self.mail_dir, recipient))
            with open(mail_path, 'a') as open_file:
                open_file.write(data + "\n")

            if self.print_messages:
                self.logger.info(data)
        """

        """
        start of modification

        todo: save downloaded file in directory according to date
        todo: to handle downloaded file type checking. ignore non JPG type of file
        """
        for part in data.walk():
            
            if part.get_content_maintype() == 'multipart':
              continue
            if part.get('Content-Disposition') is None:
              continue
            
            fileName = part.get_filename()
            if bool(fileName):
              filePath = os.path.join(self.mail_dir, fileName)
            
            # to add directory by date
            #if not os.path.isdir(os.path.join(self.mail_dir, recipient)):
            #    os.mkdir(os.path.join(self.mail_dir, recipient))
            
            if not os.path.isfile(filePath) :
                fp = open(filePath, 'wb')
                fp.write(part.get_payload(decode=True))
                fp.close()
            
            subject = str(data).split("Subject: ", 1)[1].split("\nTo:", 1)[0]
            self.logger.info('Downloaded "{file}" from email titled "{subject}".'.format(file=fileName, subject=subject))
            
            #if self.print_messages:
            #    self.logger.info(data)
        
        return '250 OK'


def _parse_args():
    """
    Parse the CLI arguments for use by NullSMTPD.

    :return: namespace containing the arguments parsed from the CLI
    """
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--no-fork", action="store_true",
                        help="Don't fork and run nullsmtpd as a daemon. Additionally, this will "
                             "print all log messages to stdout/stderr and all emails to stdout.")
    parser.add_argument("-H", "--host", type=str, default="localhost",
                        help="Host to listen on (defaults to localhost)")
    parser.add_argument("-P", "--port", type=int, default=25,
                        help="Port to listen on (defaults to 25)")
    parser.add_argument("--mail-dir", type=str, default=NULLSMTPD_DIRECTORY,
                        help="Location to write logs and emails (defaults to ~/.nullsmtpd)")
    parser.add_argument("-v", "--version", action="version", version="%(prog)s ("+__version__+")")
    return parser.parse_args()


def main():
    """
    Main process where we get the CLI arguments, set up our loggers and then start NullSMTP,
    either running it as a daemon (default behavior) or interactively based on a passed in flag.
    """
    args = _parse_args()
    if not os.path.isdir(args.mail_dir):
        os.mkdir(args.mail_dir)

    if args.no_fork is not True:
        pid = os.fork()
        if pid != 0:
            raise SystemExit("Could not fork nullsmtpd")

    host = args.host
    port = args.port
    output_messages = 'no_fork' in args and args.no_fork
    logger = configure_logging(args.mail_dir, output_messages)
    mail_dir = args.mail_dir

    logger.info(
        "Starting nullsmtpd {:s} on {:s}:{:d}".format(
            __version__,
            host,
            port
        )
    )
    loop = asyncio.get_event_loop()
    nullsmtpd = NullSMTPDHandler(logger, mail_dir, output_messages)
    controller = MyController(nullsmtpd, hostname=host, port=port)
    controller.start()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info('Stopping nullsmtpd')
        controller.stop()
        loop.stop()


if __name__ == "__main__":
    main()
