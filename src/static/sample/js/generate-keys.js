rsaKeyPair =
{
    publicKey: "",
    privateKey: "",
};

const generateRSAKey = async () => {
    rsaKeyPair = await dbGenerateRSAKeys();
    //document.getElementById("demo").innerHTML = rsaKeyPair.publicKey + "<br><br><br>" + rsaKeyPair.privateKey;
};

const downloadPemFile = (content, fileName) => {
    const link = document.createElement("a");
    const file = new Blob([content], { type: "text/plain" });
    link.href = URL.createObjectURL(file);
    link.download = fileName;
    link.click();
    URL.revokeObjectURL(link.href);
};

const downloadPemFiles = () => {
    if (rsaKeyPair.privateKey) {
      downloadPemFile(rsaKeyPair.privateKey, "rsa_private.pem");
    }
    if (rsaKeyPair.publicKey) {
      downloadPemFile(rsaKeyPair.publicKey, "rsa_public.pem");
    }
};

const generateAndDownloadKeys = async () => {
    generateRSAKey();
    downloadPemFiles();
}