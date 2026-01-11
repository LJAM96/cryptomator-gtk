import org.cryptomator.cryptofs.CryptoFileSystemProperties;
import org.cryptomator.cryptofs.CryptoFileSystemProvider;
import java.nio.file.Path;
import java.nio.file.Paths;

public class VaultInitializer {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("Usage: java VaultInitializer <vault-path> <password>");
            System.exit(1);
        }
        
        try {
            Path vaultPath = Paths.get(args[0]);
            String password = args[1];
            
            CryptoFileSystemProvider provider = new CryptoFileSystemProvider();
            CryptoFileSystemProperties properties = CryptoFileSystemProperties.cryptoFileSystemProperties()
                .withPassphrase(password)
                .build();
            
            provider.initialize(vaultPath, properties);
            
            System.out.println("Vault initialized successfully");
            System.exit(0);
        } catch (Exception e) {
            System.err.println("Failed to initialize vault: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }
}
