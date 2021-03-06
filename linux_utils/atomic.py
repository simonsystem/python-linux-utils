# linux-utils: Linux system administration tools for Python.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: June 24, 2017
# URL: https://linux-utils.readthedocs.io

"""
Atomic filesystem operations for Linux in Python.

The most useful functions in this module are :func:`make_dirs()`,
:func:`touch()`, :func:`write_contents()` and :func:`write_file()`.

The :func:`copy_stat()` and :func:`get_temporary_file()` functions were
originally part of the logic in :func:`write_file()` but have since been
extracted to improve the readability and reusability of the code.
"""

# Standard library modules.
import codecs
import contextlib
import errno
import logging
import os
import stat

# External dependencies.
from humanfriendly import Timer
from six import text_type

# Public identifiers that require documentation.
__all__ = (
    'copy_stat',
    'get_temporary_file',
    'make_dirs',
    'touch',
    'write_contents',
    'write_file',
)

# Initialize a logger for this module.
logger = logging.getLogger(__name__)


def copy_stat(filename, reference=None, mode=None, uid=None, gid=None):
    """
    The Python equivalent of ``chmod --reference && chown --reference``.

    :param filename: The pathname of the file whose permissions and
                     ownership should be modified (a string).
    :param reference: The pathname of the file to use as
                      reference (a string or :data:`None`).
    :param mode: The permissions to set when `reference` isn't given or doesn't
                 exist (a number or :data:`None`).
    :param uid: The user id to set when `reference` isn't given or doesn't
                exist (a number or :data:`None`).
    :param gid: The group id to set when `reference` isn't given or doesn't
                exist (a number or :data:`None`).
    """
    # Try to get the metadata from the reference file.
    try:
        if reference:
            metadata = os.stat(reference)
            mode = stat.S_IMODE(metadata.st_mode)
            uid = metadata.st_uid
            gid = metadata.st_gid
            logger.debug("Copying permissions and ownership (%s) ..", reference)
    except OSError as e:
        # The only exception that we want to swallow
        # is when the reference file doesn't exist.
        if e.errno != errno.ENOENT:
            raise
    # Change the file's permissions?
    if mode is not None:
        logger.debug("Changing file permissions (%s) to %o ..", filename, mode)
        os.chmod(filename, mode)
    # Change the file's ownership?
    if uid is not None or gid is not None:
        logger.debug("Changing owner (%s) and group (%s) of file (%s) ..",
                     "unchanged" if uid is None else uid,
                     "unchanged" if gid is None else gid,
                     filename)
        os.chown(filename, -1 if uid is None else uid, -1 if gid is None else gid)


def get_temporary_file(filename):
    """
    Generate a non-obtrusive temporary filename.

    :param filename: The filename on which the name of the temporary file
                     should be based (a string).
    :returns: The filename of a temporary file (a string).

    This function tries to generate the most non-obtrusive temporary filenames:

    1. The temporary file will be located in the same directory as the file to
       replace,  because this is the only location somewhat guaranteed to
       support "rename into place" semantics (see :func:`write_file()`).
    2. The temporary file will be hidden from directory listings and common
       filename patterns because it has a leading dot.
    3. The temporary file will have a different extension then the file to
       replace (in case of filename patterns that do match dotfiles).
    4. The temporary filename has a decent chance of not conflicting with
       temporary filenames generated by concurrent processes.
    """
    directory, basename = os.path.split(filename)
    return os.path.join(directory, '.%s.tmp-%i' % (basename, os.getpid()))


def make_dirs(directory, mode=0o777):
    """
    Create a directory if it doesn't already exist (keeping concurrency in mind).

    :param directory: The pathname of a directory (a string).
    :returns: :data:`True` if the directory was created,
              :data:`False` if it already existed.
    :raises: Any exceptions raised by :func:`os.makedirs()`.

    This function is a wrapper for :func:`os.makedirs()` that swallows
    :exc:`~exceptions.OSError` in the case of :data:`~errno.EEXIST`.
    """
    try:
        logger.debug("Trying to create directory (%s) ..", directory)
        os.makedirs(directory, mode)
        logger.debug("Successfully created directory.")
        return True
    except OSError as e:
        if e.errno == errno.EEXIST:
            # The directory already exists.
            logger.debug("Directory already exists.")
            return False
        else:
            # Don't swallow errors other than EEXIST because we don't
            # want to obscure real problems (e.g. permission denied).
            logger.debug("Failed to create directory, propagating exception!")
            raise


def touch(filename):
    """
    The equivalent of the touch_ program in Python.

    :param filename: The pathname of the file to touch (a string).

    This function uses :func:`make_dirs()` to automatically create missing
    directory components in `filename`.

    .. _touch: https://manpages.debian.org/touch
    """
    logger.debug("Touching file: %s", filename)
    make_dirs(os.path.dirname(filename))
    with open(filename, 'a'):
        os.utime(filename, None)


def write_contents(filename, contents, encoding='UTF-8', mode=None):
    """
    Atomically create or update a file's contents.

    :param filename: The pathname of the file (a string).
    :param contents: The (new) contents of the file (a
                     byte string or a Unicode string).
    :param encoding: The text encoding used to encode `contents`
                     when it is a Unicode string.
    :param mode: The permissions to use when the file doesn't exist yet (a
                 number like accepted by :func:`os.chmod()` or :data:`None`).
    """
    if isinstance(contents, text_type):
        contents = codecs.encode(contents, encoding)
    with write_file(filename, mode=mode) as handle:
        handle.write(contents)


@contextlib.contextmanager
def write_file(filename, mode=None):
    """
    Atomically create or update a file (avoiding partial reads).

    :param filename: The pathname of the file (a string).
    :param mode: The permissions to use when the file doesn't exist yet (a
                 number like accepted by :func:`os.chmod()` or :data:`None`).
    :returns: A writable file object whose contents will be used to create or
              atomically replace `filename`.
    """
    timer = Timer()
    logger.debug("Preparing to create or atomically replace file (%s) ..", filename)
    make_dirs(os.path.dirname(filename))
    temporary_file = get_temporary_file(filename)
    logger.debug("Opening temporary file for writing (%s) ..", temporary_file)
    with open(temporary_file, 'wb') as handle:
        yield handle
    copy_stat(filename=temporary_file, reference=filename, mode=mode)
    logger.debug("Moving new contents into place (%s -> %s) ..", temporary_file, filename)
    os.rename(temporary_file, filename)
    logger.debug("Took %s to create or replace file.", timer)
