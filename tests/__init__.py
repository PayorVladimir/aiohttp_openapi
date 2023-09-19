import logging

test_logger = logging.getLogger(__name__)
test_logger.setLevel(logging.DEBUG)
test_logger.addHandler(logging.StreamHandler())
