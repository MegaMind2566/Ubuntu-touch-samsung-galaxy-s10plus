use samloader_fus::FusClient;
use serde_json::json;

fn main() {
    const REQUESTED: &str = "G975FXXSGHWC1/G975FOXMGHWA3/G975FXXSGHWB3/G975FXXSGHWC1";
    // BinaryInform is metadata only: do not initialize a download, request the
    // firmware body, access USB, or print authentication/decryption material.
    let result = std::panic::catch_unwind(|| {
        let mut client = FusClient::new().expect("Cannot initialize firmware metadata client");
        client.fetch_binary_info("SM-G975F", "ITV", REQUESTED);
        json!({
            "model": "SM-G975F", "region": "ITV", "requested_version": REQUESTED,
            "server_version": client.info.version,
            "server_region": client.info.region,
            "server_filename": client.info.filename,
            "firmware_bytes": client.info.size,
            "exact_binary_offered": client.info.version == REQUESTED && client.info.size > 0,
            "metadata_query_succeeded": true,
            "firmware_downloaded": false, "handset_modified": false,
            "install_ready": false,
            "samloader_source_commit": "4dfea027767f3268e70dc130f169d459bd153cbf"
        })
    });
    let report = result.unwrap_or_else(|_| json!({
        "model": "SM-G975F", "region": "ITV", "requested_version": REQUESTED,
        "metadata_query_succeeded": false, "exact_binary_offered": false,
        "firmware_downloaded": false, "handset_modified": false, "install_ready": false,
        "error": "Samsung did not return valid binary metadata for the exact requested firmware"
    }));
    println!("{}", serde_json::to_string_pretty(&report).unwrap());
}
