import backend.common.data_loader as dl


def test_list_aws_plots(s3_bucket, monkeypatch):
    s3, bucket = s3_bucket
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    s3.put_object(Bucket=bucket, Key="accounts/Alice/ISA.json", Body=b"{}")
    s3.put_object(Bucket=bucket, Key="accounts/Alice/person.json", Body=b"{}")
    s3.put_object(Bucket=bucket, Key="accounts/Bob/GIA.json", Body=b"{}")
    expected = [
        {"owner": "Alice", "accounts": ["ISA"]},
        {"owner": "Bob", "accounts": ["GIA"]},
    ]
    assert dl._list_aws_plots() == expected


def test_load_account_from_s3(s3_bucket, monkeypatch):
    s3, bucket = s3_bucket
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    s3.put_object(Bucket=bucket, Key="accounts/Alice/ISA.json", Body=b"{\"balance\": 10}")
    assert dl.load_account("Alice", "ISA") == {"balance": 10}


def test_load_person_meta_from_s3(s3_bucket, monkeypatch):
    s3, bucket = s3_bucket
    monkeypatch.setattr(dl.config, "app_env", "aws", raising=False)
    s3.put_object(Bucket=bucket, Key="accounts/Alice/person.json", Body=b"{\"dob\": \"1980\"}")
    assert dl.load_person_meta("Alice") == {"dob": "1980"}
    assert dl.load_person_meta("Bob") == {}
