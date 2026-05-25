"""Acceptance tests for ``parse_constraints``.

Each row pins down behavior in both directions: one version that must satisfy
the constraint and one that must not.
"""

import pytest

from picopip import parse_constraints, parse_version

CASES = [
    ("openai >= 1.26.0", "1.26.0", "1.25.0"),
    ("google-cloud-aiplatform >= 1.64", "1.70", "1.63"),
    ("aio_pika >= 7.2.0, < 10.0.0", "9.4.0", "10.0.0"),
    ("aiohttp ~= 3.0", "3.9.5", "4.0.0"),
    ("aiohttp ~= 3.0", "3.0.0", "2.9.0"),
    ("aiokafka >= 0.8, < 1.0", "0.9.0", "1.0.0"),
    ("aiopg >= 0.13.0, < 2.0.0", "1.4.0", "2.0.0"),
    ("asgiref ~= 3.0", "3.8.0", "2.0"),
    ("asyncclick ~= 8.0", "8.1.0", "9.0"),
    ("asyncpg >= 0.12.0", "0.30.0", "0.11.0"),
    ("boto3 ~= 1.0", "1.35.0", "2.0"),
    ("botocore ~= 1.0", "1.35.0", "2.0"),
    ("aiobotocore ~= 2.0", "2.13.0", "3.0"),
    ("cassandra-driver ~= 3.25", "3.29.0", "3.24.0"),
    ("scylla-driver ~= 3.25", "3.26.0", "3.24.0"),
    ("celery >= 4.0, < 6.0", "5.3.0", "6.0.0"),
    ("click >= 8.1.3, < 9.0.0", "8.1.7", "8.1.2"),
    ("confluent-kafka >= 1.8.2, < 3.0.0", "2.5.0", "1.8.1"),
    ("django >= 2.0", "5.0.0", "1.11"),
    ("elasticsearch >= 6.0", "8.0.0", "5.0"),
    ("falcon >= 1.4.1, < 5.0.0", "3.1.0", "5.0.0"),
    ("fastapi ~= 0.92", "0.95.0", "1.0"),
    ("flask >= 1.0", "3.0.0", "0.12"),
    ("grpcio >= 1.42.0", "1.62.0", "1.41.0"),
    ("httpx >= 0.18.0", "0.27.0", "0.17.0"),
    ("jinja2 >= 2.7, < 4.0", "3.1.0", "4.0.0"),
    ("kafka-python >= 2.0, < 3.0", "2.0.2", "3.0.0"),
    ("kafka-python-ng >= 2.0, < 3.0", "2.2.0", "3.0.0"),
    ("mysql-connector-python >= 8.0, < 10.0", "9.0.0", "10.0.0"),
    ("mysqlclient < 3", "2.2.0", "3.0.0"),
    ("pika >= 0.12.0", "1.3.0", "0.11"),
    ("psycopg >= 3.1.0", "3.2.0", "3.0.0"),
    ("psycopg2 >= 2.7.3.1", "2.9.0", "2.7.3"),
    ("psycopg2-binary >= 2.7.3.1", "2.9.0", "2.7.0"),
    ("pymemcache >= 1.3.5, < 5", "4.0.0", "5.0.0"),
    ("pymongo >= 3.1, < 5.0", "4.6.0", "5.0.0"),
    ("pymssql >= 2.1.5, < 3", "2.2.0", "3.0.0"),
    ("PyMySQL < 2", "1.1.0", "2.0.0"),
    ("pyramid >= 1.7", "2.0.0", "1.6"),
    ("redis >= 2.6", "5.0.0", "2.5"),
    ("remoulade >= 0.50", "0.60", "0.49"),
    ("requests ~= 2.0", "2.31.0", "3.0"),
    ("sqlalchemy >= 1.0.0, < 2.1.0", "2.0.0", "2.1.0"),
    ("starlette >= 0.13", "0.36", "0.12"),
    ("psutil >= 5", "5.9.0", "4.0"),
    ("tornado >= 5.1.1", "6.4", "5.1.0"),
    ("tortoise-orm >= 0.17.0", "0.21.0", "0.16.0"),
    ("pydantic >= 1.10.2", "2.0.0", "1.10.1"),
    ("urllib3 >= 1.0.0, < 3.0.0", "2.2.0", "3.0.0"),
    ("foo == 1.0.0", "1.0.0", "1.0.1"),
    ("foo != 1.0.0", "1.0.1", "1.0.0"),
    ("foo <= 2.0", "2.0", "2.1"),
    ("foo > 1.0", "1.0.1", "1.0"),
    ("foo >= 1.0, != 1.5, < 2.0", "1.4", "1.5"),
    (">= 0.5, < 1.0", "0.7", "1.0"),                  # bare spec, no name
    ("foo>=1.0,<2.0", "1.5", "2.0"),                  # no whitespace
    ("foo ~= 1.4.5", "1.4.10", "1.5.0"),              # 3-segment ~=
    ("foo >= 1.0", "1.0", "1.0rc1"),                  # pre-release ordering
]


@pytest.mark.parametrize(("spec", "matching", "non_matching"), CASES)
def test_constraint_satisfaction(spec, matching, non_matching):
    constraints = parse_constraints(spec)

    matching_v = parse_version(matching)
    assert all(op(matching_v, cv) for op, cv in constraints), (
        f"{matching!r} should satisfy {spec!r}"
    )

    non_matching_v = parse_version(non_matching)
    assert not all(op(non_matching_v, cv) for op, cv in constraints), (
        f"{non_matching!r} should not satisfy {spec!r}"
    )


def test_tilde_eq_rejects_single_segment():
    with pytest.raises(ValueError, match="~= requires a multi-segment version"):
        parse_constraints("foo ~= 1")
