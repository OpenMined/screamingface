from url4.streaming.protocol import OutboundFrame, OutboundFrameAdapter


def encode(event: OutboundFrame) -> bytes:
    return OutboundFrameAdapter.dump_json(event, by_alias=True)


def decode(payload: bytes, sequence: int | None = None) -> OutboundFrame:
    # WHY validate_json and not json.loads + validate_python: the latter builds a throwaway dict
    # for every frame on the stream. Result bodies run to `result_cap` (1 MiB), and a sync GET
    # decodes the whole run a second time.
    event = OutboundFrameAdapter.validate_json(payload)
    if sequence is not None:
        event = event.model_copy(update={"sequence": str(sequence), "sequencetype": "Integer"})
    return event


__all__ = ["decode", "encode"]
