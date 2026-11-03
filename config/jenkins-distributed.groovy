// One-time init script for the migrated controller. Never commit key material.
import jenkins.model.Jenkins
import jenkins.model.JenkinsLocationConfiguration
import hudson.model.Node
import hudson.slaves.DumbSlave
import hudson.slaves.JNLPLauncher
import hudson.slaves.RetentionStrategy
import hudson.plugins.git.GitSCM
import hudson.plugins.git.BranchSpec
import hudson.plugins.git.UserRemoteConfig
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey

def j = Jenkins.get()
j.setNumExecutors(0)
j.setLabelString('controller')
j.setSlaveAgentPort(-1)
def launcher = new JNLPLauncher()
launcher.setWebSocket(true)
if (j.getNode('linux-socketcan-129') == null) {
    def node = new DumbSlave('linux-socketcan-129',
        'Dedicated SocketCAN agent on 192.168.222.129',
        '/var/lib/adas-jenkins-agent', '1', Node.Mode.EXCLUSIVE,
        'linux-socketcan', launcher, new RetentionStrategy.Always(), [])
    j.addNode(node)
}
def keyFile = new File(j.rootDir, 'migration-scm-key')
if (keyFile.exists()) {
    def provider = SystemCredentialsProvider.getInstance()
    if (!provider.getCredentials().any { it.id == 'adas-source-readonly' }) {
        def credential = new BasicSSHUserPrivateKey(CredentialsScope.GLOBAL,
            'adas-source-readonly', 'ice',
            new BasicSSHUserPrivateKey.DirectEntryPrivateKeySource(keyFile.text),
            null, 'Read-only source Git via forced git-upload-pack on .129')
        provider.getStore().addCredentials(Domain.global(), credential)
    }
}
def job = j.getItem('adas-validation')
assert job != null
def scm = new GitSCM([new UserRemoteConfig(
    'ssh://ice@192.168.222.129/home/ice/projects/adas-integration-lab',
    null, null, 'adas-source-readonly')],
    [new BranchSpec('*/main')], false, [], null, null, [])
job.setDefinition(new CpsScmFlowDefinition(scm, 'Jenkinsfile'))
job.save()
// Keep historical failure evidence; its disposable local fixture was not migrated.
def failure = j.getItem('adas-failure-validation')
if (failure != null) {
    failure.setDisabled(true)
    failure.save()
}
def location = JenkinsLocationConfiguration.get()
location.setUrl('http://jenkins.ice.tech/')
location.save()
new File(j.rootDir, 'migration-agent-secret').text =
    j.getNode('linux-socketcan-129').toComputer().getJnlpMac()
j.save()
println('Distributed controller configured; built-in executors=0')
